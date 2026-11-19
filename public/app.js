const form = document.getElementById("ask");
const statusLine = document.getElementById("status");
const button = document.getElementById("run");
const output = document.getElementById("out");
const answer = document.getElementById("answer");
const evidence = document.getElementById("evidence");

function showEvidence(records) {
  evidence.replaceChildren();

  for (const record of records) {
    const heading = document.createElement("h3");
    heading.textContent =
      `${record.source_file} — data record ${record.source_record}`;

    const table = document.createElement("table");
    const body = document.createElement("tbody");

    for (const [field, value] of Object.entries(record.values)) {
      const row = document.createElement("tr");
      const label = document.createElement("th");
      const cell = document.createElement("td");

      label.scope = "row";
      label.textContent = field;
      cell.textContent = value === "" || value == null
        ? "Not recorded"
        : String(value);

      row.append(label, cell);
      body.append(row);
    }

    table.append(body);
    evidence.append(heading, table);
  }
}

form.addEventListener("submit", async (event) => {
  event.preventDefault();

  const question = document.getElementById("q").value.trim().toUpperCase();

  output.hidden = true;
  evidence.replaceChildren();

  if (!/^CLM-\d{4}-\d{5}$/.test(question)) {
    statusLine.textContent =
      "Enter a claim number such as CLM-2404-04177.";
    return;
  }

  button.disabled = true;
  statusLine.textContent = "Looking up claim…";

  try {
    const response = await fetch("/api/ask", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ question }),
    });

    const data = await response.json();

    if (!response.ok) {
      throw new Error(data.error || `Request failed: ${response.status}`);
    }

    answer.textContent = data.answer;
    showEvidence(data.evidence || []);
    output.hidden = false;

    const labels = {
      found: "Record found",
      not_found: "Not found",
      needs_review: "Needs a person",
      invalid_input: "Check input",
    };

    statusLine.textContent = labels[data.status] || "Complete";

  } catch (error) {
    statusLine.textContent = `Lookup failed: ${error.message}`;
  } finally {
    button.disabled = false;
  }
});