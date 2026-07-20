(() => {
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

  const capabilitySelect = document.getElementById("capability-select");
  const stateSelect = document.getElementById("state-select");
  const districtSelect = document.getElementById("district-select");
  const searchBtn = document.getElementById("search-btn");
  const resultsList = document.getElementById("results-list");
  const errorBanner = document.getElementById("error-banner");
  const modeBanner = document.getElementById("mode-banner");
  const cardTemplate = document.getElementById("facility-card-template");

  let regionsByState = {};
  let currentFacilities = [];
  const detailCache = new Map();

  function showError(err) {
    errorBanner.textContent = err.message || String(err);
    errorBanner.classList.remove("hidden");
  }
  function clearError() {
    errorBanner.classList.add("hidden");
  }

  function updateSearchEnabled() {
    searchBtn.disabled = !(capabilitySelect.value && stateSelect.value);
  }

  async function loadMeta() {
    try {
      const meta = await Api.getMeta();
      modeBanner.textContent = `Connected to Databricks (${meta.trust_table})`;
      modeBanner.classList.add("connected");
    } catch (err) {
      modeBanner.textContent = "Could not connect to Databricks";
      modeBanner.classList.add("error");
    }
  }

  async function loadCapabilities() {
    const { capabilities } = await Api.getCapabilities();
    capabilitySelect.innerHTML = '<option value="">Select a capability…</option>' +
      capabilities.map((c) => `<option value="${c}">${labelFor(c)}</option>`).join("");
  }

  async function loadRegions() {
    const { regions } = await Api.getRegions();
    regionsByState = {};
    regions.forEach(({ state, district }) => {
      (regionsByState[state] ||= []).push(district);
    });
    const states = Object.keys(regionsByState).sort();
    stateSelect.innerHTML = '<option value="">Select a state…</option>' +
      states.map((s) => `<option value="${s}">${s}</option>`).join("");
  }

  function onStateChange() {
    const districts = regionsByState[stateSelect.value] || [];
    districtSelect.innerHTML = '<option value="">Any district</option>' +
      districts.map((d) => `<option value="${d}">${d}</option>`).join("");
    updateSearchEnabled();
  }

  const TIER_ORDER = ["High", "Medium", "Low"];
  let activeTier = "High";

  function buildFacilityCard(facility) {
    const node = cardTemplate.content.cloneNode(true);
    const card = node.querySelector(".facility-card");
    card.dataset.uniqueId = facility.unique_id;
    node.querySelector(".facility-name").textContent = facility.name;
    node.querySelector(".facility-location").textContent = `${facility.district}, ${facility.state}`;
    const pill = node.querySelector(".trust-pill");
    pill.textContent = `${facility.trust_level} · ${facility.trust_score}/100`;
    pill.classList.add(facility.trust_level);
    node.querySelector(".facility-explanation").textContent = facility.explanation;

    const toggle = node.querySelector(".expand-toggle");
    const detailEl = node.querySelector(".facility-detail");
    toggle.addEventListener("click", () => toggleExpand(facility.unique_id, toggle, detailEl));
    return node;
  }

  // Results are split into High/Medium/Low confidence sub-tabs rather than one
  // long mixed list — clicking a tier shows only its facilities, on the card
  // list and the map alike, instead of dumping everything from one search.
  function renderResults(facilities) {
    currentFacilities = facilities;
    resultsList.innerHTML = "";
    if (!facilities.length) {
      resultsList.innerHTML = '<div class="empty-state" role="status">No facilities matched this capability + region. ' +
        "This may be a data desert (we don't know) rather than a medical desert — check the Medical Desert Planner tab for that distinction.</div>";
      TrustMap.renderPins([]);
      return;
    }

    const byTier = { High: [], Medium: [], Low: [] };
    facilities.forEach((f) => (byTier[f.trust_level] || (byTier[f.trust_level] = [])).push(f));
    activeTier = TIER_ORDER.find((t) => byTier[t].length) || TIER_ORDER[0];

    const countLine = document.createElement("p");
    countLine.className = "desert-count";
    countLine.style.padding = "0";
    countLine.textContent = `${facilities.length} facilit${facilities.length === 1 ? "y" : "ies"} found`;
    resultsList.appendChild(countLine);

    const tabBar = document.createElement("div");
    tabBar.className = "confidence-tabs";
    tabBar.setAttribute("role", "tablist");
    tabBar.setAttribute("aria-label", "Filter results by confidence");
    resultsList.appendChild(tabBar);

    const panel = document.createElement("div");
    panel.className = "confidence-panel";
    panel.setAttribute("role", "tabpanel");
    panel.setAttribute("aria-live", "polite");
    resultsList.appendChild(panel);

    function renderTierPanel() {
      tabBar.querySelectorAll("button").forEach((b) => {
        b.setAttribute("aria-selected", String(b.dataset.tier === activeTier));
        b.classList.toggle("active", b.dataset.tier === activeTier);
      });
      panel.innerHTML = "";
      const tierFacilities = byTier[activeTier] || [];
      tierFacilities.forEach((f) => panel.appendChild(buildFacilityCard(f)));
      TrustMap.renderPins(tierFacilities, (uniqueId) => scrollToCard(uniqueId));
    }

    TIER_ORDER.forEach((tier) => {
      const count = byTier[tier].length;
      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = `confidence-tab ${tier}`;
      btn.dataset.tier = tier;
      btn.textContent = `${tier} (${count})`;
      btn.setAttribute("role", "tab");
      btn.setAttribute("aria-selected", String(tier === activeTier));
      btn.disabled = count === 0;
      btn.addEventListener("click", () => {
        activeTier = tier;
        renderTierPanel();
      });
      tabBar.appendChild(btn);
    });

    renderTierPanel();
  }

  function scrollToCard(uniqueId) {
    const card = resultsList.querySelector(`[data-unique-id="${uniqueId}"]`);
    if (card) card.scrollIntoView({ behavior: "smooth", block: "center" });
  }

  async function toggleExpand(uniqueId, toggle, detailEl) {
    const isHidden = detailEl.classList.contains("hidden");
    if (!isHidden) {
      detailEl.classList.add("hidden");
      toggle.textContent = "Expand — evidence & notes";
      toggle.setAttribute("aria-expanded", "false");
      return;
    }
    detailEl.classList.remove("hidden");
    toggle.textContent = "Collapse";
    toggle.setAttribute("aria-expanded", "true");
    if (!detailCache.has(uniqueId)) {
      detailEl.innerHTML = '<div class="detail-loading"><span class="spinner"></span>Loading detail…</div>';
      try {
        const [detail, actionsResp] = await Promise.all([
          Api.getFacilityDetail(uniqueId),
          Api.getActions(uniqueId),
        ]);
        detailCache.set(uniqueId, { detail, actions: actionsResp.actions });
      } catch (err) {
        detailEl.innerHTML = `<div class="detail-loading">Could not load detail: ${err.message}</div>`;
        return;
      }
    }
    renderDetail(uniqueId, detailEl);
  }

  function renderDetail(uniqueId, detailEl) {
    const { detail, actions } = detailCache.get(uniqueId);

    const positiveHtml = detail.positive_evidence.length
      ? `<ul>${detail.positive_evidence.map((p) => `<li>${p}</li>`).join("")}</ul>`
      : "<p>None recorded.</p>";

    const missingHtml = detail.missing_supports.length
      ? `<ul>${detail.missing_supports.map((m) => `<li>${labelFor(m)}</li>`).join("")}</ul>`
      : "<p>None.</p>";

    const contradictionsHtml = detail.contradictions.length
      ? detail.contradictions.map((c) => `
          <div class="contradiction">
            <div class="reason">${c.reason}</div>
            ${c.evidence ? `<blockquote>&ldquo;${c.evidence}&rdquo;</blockquote>` : ""}
          </div>`).join("")
      : "<p>No contradictions detected.</p>";

    const capsRows = detail.caps.map((c) => `
      <tr>
        <td>${labelFor(c.capability)}</td>
        <td class="status-${c.status}">${c.status}</td>
        <td>${c.status === "uncertain" ? "—" : Math.round(c.confidence * 100) + "%"}</td>
        <td class="evidence">${c.evidence ? `&ldquo;${c.evidence}&rdquo;` : "—"}</td>
      </tr>`).join("");

    const actionsHtml = actions.length
      ? `<div class="actions-list">${actions.map(renderAction).join("")}</div>`
      : "<p>No planner notes yet.</p>";

    detailEl.innerHTML = `
      <div class="detail-section">
        <h4>Why this ranking</h4>
        <p>${detail.explanation}</p>
      </div>
      <div class="detail-section">
        <h4>Positive evidence</h4>
        ${positiveHtml}
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
        <h4>Full capability evidence</h4>
        <table class="caps-table">
          <thead><tr><th>Capability</th><th>Status</th><th>Confidence</th><th>Evidence</th></tr></thead>
          <tbody>${capsRows}</tbody>
        </table>
      </div>
      <div class="detail-section">
        <h4>Planner notes</h4>
        ${actionsHtml}
        ${renderNoteForm(uniqueId)}
      </div>
    `;
    wireNoteForm(uniqueId, detailEl);
  }

  function renderAction(action) {
    const when = new Date(action.created_at).toLocaleString();
    const overrideBadge = action.action_type === "override"
      ? `<span class="override-badge">OVERRIDE → ${action.override_trust_level}</span>` : "";
    return `
      <div class="action-item">
        <div>${action.note_text}${overrideBadge}</div>
        <div class="meta">${action.planner_name} · ${when}</div>
      </div>`;
  }

  function renderNoteForm(uniqueId) {
    const savedName = localStorage.getItem("sahara_planner_name") || "";
    return `
      <form class="note-form" data-unique-id="${uniqueId}">
        <div class="note-form-row">
          <input type="text" name="planner_name" placeholder="Your name" value="${savedName}" />
          <select name="action_type">
            <option value="note">Add a note</option>
            <option value="override">Override trust level</option>
          </select>
          <select name="override_trust_level" class="hidden">
            <option value="High">High</option>
            <option value="Medium">Medium</option>
            <option value="Low">Low</option>
          </select>
        </div>
        <textarea name="note_text" rows="2" placeholder="e.g. Called 7/18, confirmed ventilator on-site." required></textarea>
        <button type="submit">Save</button>
      </form>`;
  }

  function wireNoteForm(uniqueId, detailEl) {
    const form = detailEl.querySelector(".note-form");
    const actionTypeSelect = form.querySelector('[name="action_type"]');
    const overrideSelect = form.querySelector('[name="override_trust_level"]');
    actionTypeSelect.addEventListener("change", () => {
      overrideSelect.classList.toggle("hidden", actionTypeSelect.value !== "override");
    });
    form.addEventListener("submit", async (e) => {
      e.preventDefault();
      clearError();
      const plannerName = form.planner_name.value.trim() || "Anonymous planner";
      localStorage.setItem("sahara_planner_name", plannerName);
      const payload = {
        action_type: actionTypeSelect.value,
        note_text: form.note_text.value.trim(),
        planner_name: plannerName,
        override_trust_level: actionTypeSelect.value === "override" ? overrideSelect.value : null,
      };
      try {
        await Api.addAction(uniqueId, payload);
        const actionsResp = await Api.getActions(uniqueId);
        const cached = detailCache.get(uniqueId);
        cached.actions = actionsResp.actions;
        renderDetail(uniqueId, detailEl);
      } catch (err) {
        showError(err);
      }
    });
  }

  async function runSearch() {
    clearError();
    resultsList.innerHTML = '<p class="empty-hint"><span class="spinner"></span>Searching…</p>';
    try {
      const { facilities } = await Api.searchFacilities(
        capabilitySelect.value, stateSelect.value, districtSelect.value || null,
      );
      renderResults(facilities);
    } catch (err) {
      resultsList.innerHTML = "";
      showError(err);
    }
  }

  // ---- NL query: an alternate entry point into this same view, per
  // ARCHITECTURE.md's request flow ("picks capability + region, OR types
  // NL question") — reuses renderResults/TrustMap/showError as-is.
  const nlQueryForm = document.getElementById("nl-query-form");
  const nlQueryInput = document.getElementById("nl-query-input");
  const nlQueryStatus = document.getElementById("nl-query-status");

  async function runNLQuery(question) {
    clearError();
    nlQueryStatus.classList.remove("hidden");
    nlQueryStatus.innerHTML = '<span class="spinner"></span>Thinking…';
    resultsList.innerHTML = '<p class="empty-hint"><span class="spinner"></span>Searching…</p>';
    try {
      const result = await Api.nlQuery(question);
      const f = result.interpreted_filter;
      const chips = [f.capability && labelFor(f.capability), f.state, f.district,
                     f.trust_level && `trust: ${f.trust_level}`,
                     f.min_trust_score != null && `score ≥ ${f.min_trust_score}`]
                     .filter(Boolean).join(" · ") || "no filters recognized";
      const via = result.used_llm ? "via LLM" : "via keyword match (LLM unavailable)";
      nlQueryStatus.innerHTML = `<div>Interpreted as: ${chips} (${via})</div>` +
        (result.warnings.length ? `<ul class="nl-warnings">${result.warnings.map((w) => `<li>${w}</li>`).join("")}</ul>` : "") +
        (result.summary ? `<p class="nl-summary">${result.summary}</p>` : "");
      if (result.desert_records && result.desert_records.length) {
        resultsList.innerHTML = `<div class="empty-state">This looks like a coverage/desert ` +
          `question — ${result.desert_records.length} matching district × capability record(s). ` +
          `See the Data Readiness Desk tab for the full list.</div>`;
        TrustMap.renderPins([]);
      } else {
        renderResults(result.facilities);
      }
    } catch (err) {
      nlQueryStatus.classList.add("hidden");
      resultsList.innerHTML = "";
      showError(err);
    }
  }

  nlQueryForm.addEventListener("submit", (e) => {
    e.preventDefault();
    const q = nlQueryInput.value.trim();
    if (q) runNLQuery(q);
  });

  async function init() {
    TrustMap.init();
    capabilitySelect.addEventListener("change", updateSearchEnabled);
    stateSelect.addEventListener("change", onStateChange);
    searchBtn.addEventListener("click", runSearch);
    try {
      await Promise.all([loadMeta(), loadCapabilities(), loadRegions()]);
    } catch (err) {
      showError(err);
    }
  }

  document.addEventListener("DOMContentLoaded", init);
})();
