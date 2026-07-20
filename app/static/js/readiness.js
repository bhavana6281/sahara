const ReadinessDesk = (() => {
  const CAPABILITY_LABELS = {
    icu: "ICU", oxygen: "Oxygen Supply", ventilator: "Ventilator",
    neonatal: "Neonatal / NICU", pediatric: "Pediatric Specialist",
    dialysis: "Dialysis", oncology: "Oncology", trauma: "Trauma / Casualty",
    emergency_surgery: "Emergency Surgery", operation_theatre: "Operation Theatre",
    surgeon: "Surgeon", anesthesiologist: "Anesthesiologist", blood_bank: "Blood Bank",
    nurse: "Nursing Staff", physician: "Physician", "24x7": "24/7 Availability",
  };
  const labelFor = (cap) => CAPABILITY_LABELS[cap] ||
    cap.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
  const CRITICAL_CAPS = ["icu", "emergency_surgery", "oncology", "trauma", "neonatal"];
  const DECISION_LABELS = {
    confirmed_issue: "Confirmed issue", looks_fine: "Looks fine",
    needs_field_check: "Needs field check", corrected: "Corrected",
  };

  let summaryEl, filterSelect, sortSelect, refreshBtn, errorBanner, countEl, tbody;
  let queue = [];
  let initialized = false;
  let requestSeq = 0;

  function showError(err) {
    errorBanner.textContent = err.message || String(err);
    errorBanner.classList.remove("hidden");
  }
  function clearError() { errorBanner.classList.add("hidden"); }

  async function loadSummary() {
    try {
      const s = await Api.getReadinessSummary();
      summaryEl.innerHTML = `
        <div class="stat-tile"><span class="stat-value">${s.total_facilities.toLocaleString()}</span><span class="stat-label">Total records</span></div>
        <div class="stat-tile"><span class="stat-value">${s.with_contradictions.toLocaleString()}</span><span class="stat-label">With contradictions</span></div>
        <div class="stat-tile"><span class="stat-value">${s.low_trust.toLocaleString()}</span><span class="stat-label">Low trust</span></div>
        <div class="stat-tile"><span class="stat-value">${s.with_missing.toLocaleString()}</span><span class="stat-label">With missing evidence</span></div>
      `;
    } catch (err) {
      summaryEl.innerHTML = "";
      showError(err);
    }
  }

  function leverageReasons(row) {
    const parts = [];
    const claimed = row.matched_capabilities.filter((c) => CRITICAL_CAPS.includes(c));
    if (claimed.length) parts.push(`claims ${claimed.map(labelFor).join(", ")}`);
    if (row.n_contradictions) parts.push(`${row.n_contradictions} contradiction${row.n_contradictions === 1 ? "" : "s"}`);
    if (row.n_missing) parts.push(`${row.n_missing} missing support${row.n_missing === 1 ? "" : "s"}`);
    if (row.trust_level !== "High") parts.push(`${row.trust_level.toLowerCase()} trust`);
    return parts.join(" · ") || "flagged for review";
  }

  function sortQueue(rows) {
    const [key, dir] = sortSelect.value.split("-");
    const sorted = [...rows].sort((a, b) => {
      const av = a[key], bv = b[key];
      if (typeof av === "string") return dir === "asc" ? av.localeCompare(bv) : bv.localeCompare(av);
      return dir === "asc" ? av - bv : bv - av;
    });
    return sorted;
  }

  async function loadQueue() {
    clearError();
    countEl.innerHTML = '<span class="spinner"></span>Loading queue…';
    tbody.innerHTML = "";
    const thisRequest = ++requestSeq;
    try {
      const result = await Api.getReadinessQueue(filterSelect.value);
      if (thisRequest !== requestSeq) return;
      queue = result.queue;
      countEl.textContent = `${result.count} record${result.count === 1 ? "" : "s"} in the queue` +
        (filterSelect.value === "unreviewed" ? " (unreviewed only)" : " (worst first, top 200)");
      renderRows();
    } catch (err) {
      if (thisRequest !== requestSeq) return;
      countEl.textContent = "";
      showError(err);
    }
  }

  function renderRows() {
    tbody.innerHTML = "";
    sortQueue(queue).forEach((row) => tbody.appendChild(buildRow(row)));
  }

  function buildRow(row) {
    const tr = document.createElement("tr");
    tr.className = "readiness-row";
    const trustPill = `<span class="trust-pill ${row.trust_level}">${row.trust_level} · ${row.trust_score}</span>`;
    const statusBadge = row.latest_decision
      ? `<span class="decision-badge ${row.latest_decision}">${DECISION_LABELS[row.latest_decision] || row.latest_decision}</span>`
      : '<span class="decision-badge unreviewed">Unreviewed</span>';
    tr.innerHTML = `
      <td>${row.name}</td>
      <td>${row.district}, ${row.state}</td>
      <td>${trustPill}</td>
      <td>${leverageReasons(row)}</td>
      <td>${row.leverage_score}</td>
      <td>${statusBadge}</td>
    `;
    tr.style.cursor = "pointer";
    tr.addEventListener("click", () => toggleDetailRow(tr, row));
    return tr;
  }

  async function toggleDetailRow(tr, row) {
    const next = tr.nextElementSibling;
    if (next && next.classList.contains("readiness-detail-row")) {
      next.remove();
      return;
    }
    tbody.querySelectorAll(".readiness-detail-row").forEach((el) => el.remove());

    const detailTr = document.createElement("tr");
    detailTr.className = "readiness-detail-row";
    const td = document.createElement("td");
    td.colSpan = 6;
    td.innerHTML = '<div class="detail-loading"><span class="spinner"></span>Loading evidence…</div>';
    detailTr.appendChild(td);
    tr.after(detailTr);

    try {
      const [detail, decisionsResp] = await Promise.all([
        Api.getFacilityDetail(row.unique_id),
        Api.getReviewDecisions(row.unique_id),
      ]);
      renderDetail(td, row, detail, decisionsResp.decisions);
    } catch (err) {
      td.innerHTML = `<div class="detail-loading">Could not load detail: ${err.message}</div>`;
    }
  }

  function renderDetail(td, row, detail, decisions) {
    const contradictionsHtml = detail.contradictions.length
      ? detail.contradictions.map((c) => `
          <div class="contradiction">
            <div class="reason">${c.reason}</div>
            ${c.evidence ? `<blockquote>&ldquo;${c.evidence}&rdquo;</blockquote>` : ""}
          </div>`).join("")
      : "<p>No contradictions detected.</p>";

    const missingHtml = detail.missing_supports.length
      ? `<ul>${detail.missing_supports.map((m) => `<li>${labelFor(m)}</li>`).join("")}</ul>`
      : "<p>None.</p>";

    const decisionsHtml = decisions.length
      ? `<div class="actions-list">${decisions.map((d) => `
          <div class="action-item">
            <div><span class="decision-badge ${d.decision}">${DECISION_LABELS[d.decision] || d.decision}</span> ${d.note || ""}</div>
            <div class="meta">${d.reviewer} · ${new Date(d.reviewed_at).toLocaleString()}</div>
          </div>`).join("")}</div>`
      : "<p>No review decisions recorded yet.</p>";

    const savedReviewer = localStorage.getItem("sahara_reviewer_name") || "";

    td.innerHTML = `
      <div class="detail-section">
        <h4>Why this ranking</h4>
        <p>${detail.explanation}</p>
      </div>
      <div class="detail-section">
        <h4>Contradictions</h4>
        ${contradictionsHtml}
      </div>
      <div class="detail-section">
        <h4>Missing supports</h4>
        ${missingHtml}
      </div>
      <div class="detail-section">
        <h4>Review decisions</h4>
        ${decisionsHtml}
      </div>
      <div class="detail-section">
        <h4>Record a decision</h4>
        <form class="note-form review-decision-form">
          <div class="note-form-row">
            <input type="text" name="reviewer" placeholder="Your name" value="${savedReviewer}" />
            <select name="decision">
              <option value="confirmed_issue">Confirmed issue</option>
              <option value="looks_fine">Looks fine</option>
              <option value="needs_field_check">Needs field check</option>
              <option value="corrected">Corrected</option>
            </select>
          </div>
          <textarea name="note" rows="2" placeholder="Optional note, e.g. what you verified"></textarea>
          <button type="submit">Save decision</button>
        </form>
      </div>
    `;

    const form = td.querySelector(".review-decision-form");
    form.addEventListener("submit", async (e) => {
      e.preventDefault();
      clearError();
      const reviewer = form.reviewer.value.trim() || "Anonymous reviewer";
      localStorage.setItem("sahara_reviewer_name", reviewer);
      try {
        await Api.addReviewDecision(row.unique_id, {
          decision: form.decision.value,
          note: form.note.value.trim(),
          leverage_score: row.leverage_score,
          reviewer,
        });
        const decisionsResp = await Api.getReviewDecisions(row.unique_id);
        row.latest_decision = form.decision.value;
        renderDetail(td, row, detail, decisionsResp.decisions);
        const tr = td.closest("tr").previousElementSibling;
        if (tr) {
          const statusCell = tr.children[5];
          statusCell.innerHTML = `<span class="decision-badge ${row.latest_decision}">${DECISION_LABELS[row.latest_decision]}</span>`;
        }
      } catch (err) {
        showError(err);
      }
    });
  }

  function init() {
    if (initialized) return;
    initialized = true;
    summaryEl = document.getElementById("readiness-summary");
    filterSelect = document.getElementById("readiness-filter-select");
    sortSelect = document.getElementById("readiness-sort-select");
    refreshBtn = document.getElementById("readiness-refresh-btn");
    errorBanner = document.getElementById("readiness-error-banner");
    countEl = document.getElementById("readiness-count");
    tbody = document.getElementById("readiness-tbody");

    filterSelect.addEventListener("change", loadQueue);
    sortSelect.addEventListener("change", renderRows);
    refreshBtn.addEventListener("click", () => { loadSummary(); loadQueue(); });
    document.querySelectorAll("#readiness-table th[data-sort]").forEach((th) => {
      th.style.cursor = "pointer";
      th.addEventListener("click", () => {
        const key = th.dataset.sort;
        const [curKey, curDir] = sortSelect.value.split("-");
        const newDir = curKey === key && curDir === "desc" ? "asc" : "desc";
        sortSelect.value = `${key}-${newDir}`;
        renderRows();
      });
    });

    loadSummary();
    loadQueue();
  }

  return { init };
})();
