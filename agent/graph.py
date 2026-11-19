"""A minimal LangGraph tool loop: the same shape as LangGraph 3, wired for a web request.

This is a skeleton to prove your deployment works end to end. Replace it with your
own design. Keep the rules in code and give the model only the judgment calls.
"""
from typing import Annotated, TypedDict

from langchain_core.messages import AnyMessage, HumanMessage, SystemMessage, ToolMessage
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages

from agent.llm import get_llm
from agent.tools import TOOLS

MAX_TRIPS = 4
SYSTEM = (
    "You answer questions about Pfizer Limited's General Medicines trade channel for an internal user. "
    "Use the tools for every fact. If a tool returns found=false, say so. Never invent a batch, date or number."
)


class State(TypedDict):
    messages: Annotated[list[AnyMessage], add_messages]
    trips: int


def call_model(state: State) -> dict:
    llm = get_llm().bind_tools(TOOLS)
    reply = llm.invoke([SystemMessage(SYSTEM), *state["messages"]])
    return {"messages": [reply], "trips": state.get("trips", 0) + 1}


def run_tools(state: State) -> dict:
    by_name = {t.name: t for t in TOOLS}
    out = []
    for call in state["messages"][-1].tool_calls:
        result = by_name[call["name"]].invoke(call["args"])
        out.append(ToolMessage(content=str(result), tool_call_id=call["id"], name=call["name"]))
    return {"messages": out}


def route(state: State) -> str:
    last = state["messages"][-1]
    if getattr(last, "tool_calls", None) and state["trips"] < MAX_TRIPS:
        return "tools"
    return END


builder = StateGraph(State)
builder.add_node("model", call_model)
builder.add_node("tools", run_tools)
builder.add_edge(START, "model")
builder.add_conditional_edges("model", route, {"tools": "tools", END: END})
builder.add_edge("tools", "model")
graph = builder.compile()


def run_question(question: str) -> dict:
    final = graph.invoke({"messages": [HumanMessage(question)], "trips": 0})
    evidence = [m.content for m in final["messages"] if isinstance(m, ToolMessage)]
    return {"answer": final["messages"][-1].content, "evidence": evidence, "model_calls": final["trips"]}

# ---------- Claim and batch lookup: no model required ----------
import csv
import json
import re
from functools import lru_cache
from pathlib import Path
from agent.rules import compare_claim_to_batch, check_invoice, check_submission_window, check_claim_quantity
from config import CLAIM_POLICY, QUANTITY_POLICY, INVOICE_POLICY

starter_run_question = run_question
DATA_PATH = Path(__file__).resolve().parents[1] / "data"


class ClaimState(TypedDict):
    claim_no: str
    records: list[dict]
    batch_records: list[dict]
    invoice_records: list[dict]
    invoice_policy_evidence: list[dict]
    window_evidence: list[dict]
    quantity_evidence: list[dict]
    checks: list[str]
    review: bool
    result: dict


def read_index(filename, key_column, required):
    index = {}
    with open(DATA_PATH / filename, "r", encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        if not set(required).issubset(reader.fieldnames or []):
            raise ValueError(f"Required columns missing in {filename}.")
        for number, row in enumerate(reader, start=1):
            code = (row.get(key_column) or "").strip().upper()
            if code:
                index.setdefault(code, []).append({
                    "source_file": filename,
                    "source_record": number,
                    "values": dict(row),
                })
    return index


@lru_cache(maxsize=1)
def load_claim_index():
    return read_index("expiry_claims.csv", "claim_no", [
        "claim_no", "batch_no", "sku_code", "expiry_date_as_claimed"
    ])


@lru_cache(maxsize=1)
def load_batch_index():
    return read_index("batch_master.csv", "batch_no", [
        "batch_no", "sku_code", "expiry_date"
    ])


def retrieve_claim(state: ClaimState) -> dict:
    return {"records": load_claim_index().get(state["claim_no"], [])}


def verify_batch(state: ClaimState) -> dict:
    records = state["records"]
    if not records:
        return {"batch_records": [], "checks": [], "review": False}

    distinct = {json.dumps(r["values"], sort_keys=True) for r in records}
    if len(distinct) != 1:
        return {"batch_records": [], "review": True,
                "checks": ["Conflicting claim records; batch verification paused."]}

    claim = records[0]["values"]
    batch_code = (claim.get("batch_no") or "").strip().upper()
    matches = load_batch_index().get(batch_code, []) if batch_code else []
    if len(matches) != 1:
        message = (
            "Batch not found in the supplied master; archived records may be needed."
            if not matches else "Multiple batch-master records; needs review."
        )
        return {"batch_records": matches, "checks": [message], "review": True}

    comparison = compare_claim_to_batch(claim, matches[0]["values"])
    return {"batch_records": matches,
            "checks": ["Batch: found in master.", *comparison["checks"]],
            "review": not comparison["matched"]}



@lru_cache(maxsize=1)
def load_sales_index():
    return read_index("primary_sales.csv", "invoice_no", [
        "invoice_no", "invoice_date", "stockist_code", "sku_code", "batch_no", "cnf_code"
    ])


def verify_invoice(state: ClaimState) -> dict:
    records = state["records"]
    if not records:
        return {"invoice_records": []}
    if len({json.dumps(r["values"], sort_keys=True) for r in records}) != 1:
        return {"invoice_records": []}
    claim = records[0]["values"]
    reference = (claim.get("original_invoice_ref") or "").strip().upper()
    sales = load_sales_index().get(reference, []) if reference else []
    comparison = check_invoice(claim, sales)
    return {
        "invoice_records": sales,
        "invoice_policy_evidence": [INVOICE_POLICY] if not reference else [],
        "checks": [*state["checks"], *comparison["checks"]],
        "review": state["review"] or not comparison["matched"],
    }



def verify_window(state: ClaimState) -> dict:
    records = state["records"]
    if not records or len({json.dumps(r["values"], sort_keys=True) for r in records}) != 1:
        return {"window_evidence": []}
    batches = state["batch_records"]
    batch = batches[0]["values"] if len(batches) == 1 else None
    comparison = check_submission_window(
        records[0]["values"], batch, state.get("invoice_records", [])
    )
    return {
        "checks": [*state["checks"], *comparison["checks"]],
        "review": state["review"] or comparison["review"],
        "window_evidence": [CLAIM_POLICY],
    }



def verify_quantity(state: ClaimState) -> dict:
    records = state["records"]
    if not records or len({json.dumps(r["values"], sort_keys=True) for r in records}) != 1:
        return {"quantity_evidence": []}
    supplies = [r for group in load_sales_index().values() for r in group]
    claims = [r for group in load_claim_index().values() for r in group]
    comparison = check_claim_quantity(records[0]["values"], supplies, claims)
    evidence = [*comparison["evidence"], QUANTITY_POLICY]
    if comparison["summary"]:
        evidence.append({
            "source_file": "Calculated from displayed claims and primary_sales.csv evidence",
            "source_record": "Quantity comparison (derived result)",
            "values": comparison["summary"],
        })
    return {"quantity_evidence": evidence,
            "checks": [*state["checks"], *comparison["checks"]],
            "review": state["review"] or comparison["review"]}


def merge_evidence(*groups):
    result, seen = [], set()
    for group in groups:
        for record in group:
            key = json.dumps(record, sort_keys=True)
            if key not in seen:
                seen.add(key)
                result.append(record)
    return result


def present_claim(state: ClaimState) -> dict:
    if not state["records"]:
        result = {"status": "not_found",
                  "answer": "Claim not found in the supplied extract.",
                  "evidence": [], "model_calls": 0}
    else:
        checks = " ".join(state["checks"])
        result = {
            "status": "needs_review" if state["review"] else "found",
            "answer": checks + " Full eligibility and approval "
                      "checks are not complete. This is not an approval.",
            "evidence": merge_evidence(state["records"], state["batch_records"], state.get("invoice_records", []), state.get("window_evidence", []), state.get("quantity_evidence", []), state.get("invoice_policy_evidence", [])),
            "model_calls": 0,
        }
    return {"result": result}


claim_builder = StateGraph(ClaimState)
claim_builder.add_node("retrieve_claim", retrieve_claim)
claim_builder.add_node("verify_batch", verify_batch)
claim_builder.add_node("verify_invoice", verify_invoice)
claim_builder.add_node("verify_window", verify_window)
claim_builder.add_node("verify_quantity", verify_quantity)
claim_builder.add_node("present_claim", present_claim)
claim_builder.add_edge(START, "retrieve_claim")
claim_builder.add_edge("retrieve_claim", "verify_batch")
claim_builder.add_edge("verify_batch", "verify_invoice")
claim_builder.add_edge("verify_invoice", "verify_window")
claim_builder.add_edge("verify_window", "verify_quantity")
claim_builder.add_edge("verify_quantity", "present_claim")
claim_builder.add_edge("present_claim", END)
claim_graph = claim_builder.compile()


def run_question(question: str) -> dict:
    text = question.strip().upper()
    if text.startswith("CLM-"):
        if not re.fullmatch(r"CLM-\d{4}-\d{5}", text):
            return {"status": "invalid_input", "answer":
                    "Enter a claim number in the format CLM-yymm-nnnnn.",
                    "evidence": [], "model_calls": 0}
        try:
            final = claim_graph.invoke({
                "claim_no": text, "records": [], "batch_records": [], "invoice_records": [],
                "checks": [], "review": False, "result": {}, "window_evidence": [], "quantity_evidence": [],
            })
            return final["result"]
        except (OSError, csv.Error, UnicodeError):
            raise ValueError("Could not read the claims, batch or sales extract. Check data/.")
    return starter_run_question(question)
