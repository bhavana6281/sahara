(() => {
  const toggleBtn = document.getElementById("architecture-toggle");
  const closeBtn = document.getElementById("architecture-close");
  const panel = document.getElementById("architecture-panel");
  const backdrop = document.getElementById("architecture-backdrop");
  const statsEl = document.getElementById("architecture-stats");
  const llmLine = document.getElementById("arch-llm-line");

  function open() {
    panel.classList.remove("hidden");
    panel.classList.add("open");
    panel.setAttribute("aria-hidden", "false");
    backdrop.classList.remove("hidden");
    toggleBtn.setAttribute("aria-expanded", "true");
    loadStatus(); // re-fetch every time it's opened, so counts stay current
  }

  function close() {
    panel.classList.remove("open");
    panel.setAttribute("aria-hidden", "true");
    backdrop.classList.add("hidden");
    toggleBtn.setAttribute("aria-expanded", "false");
    setTimeout(() => panel.classList.add("hidden"), 250); // match CSS transition
  }

  function fmt(n) {
    return n == null ? "unavailable" : n.toLocaleString();
  }

  async function loadStatus() {
    statsEl.innerHTML = '<div class="detail-loading"><span class="spinner"></span>Loading live status…</div>';
    try {
      const s = await Api.getArchitectureStatus();
      llmLine.textContent = `NL query → ${s.llm_endpoint} emits a validated filter (never SQL) · trust is only ever looked up`;
      const t = s.tables;
      statsEl.innerHTML = `
        <h3>Live data layer</h3>
        <div class="arch-stat-grid">
          <div class="arch-stat"><span class="arch-stat-value">${fmt(t.facility_trust.row_count)}</span><span class="arch-stat-label">facility_trust rows</span></div>
          <div class="arch-stat"><span class="arch-stat-value">${fmt(t.district_desert.row_count)}</span><span class="arch-stat-label">district_desert rows</span></div>
          <div class="arch-stat"><span class="arch-stat-value">${fmt(t.planner_actions.row_count)}</span><span class="arch-stat-label">planner notes/overrides</span></div>
          <div class="arch-stat"><span class="arch-stat-value">${fmt(t.review_decisions.row_count)}</span><span class="arch-stat-label">review decisions</span></div>
        </div>
        <p class="arch-connection">Connected to <code>${s.databricks_host}</code></p>
      `;
    } catch (err) {
      statsEl.innerHTML = `<p>Could not load live status: ${err.message}</p>`;
    }
  }

  toggleBtn.addEventListener("click", () => {
    if (panel.classList.contains("open")) close(); else open();
  });
  closeBtn.addEventListener("click", close);
  backdrop.addEventListener("click", close);
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape" && panel.classList.contains("open")) close();
  });
})();
