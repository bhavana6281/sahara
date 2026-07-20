const DesertApp = (() => {
  const CAPABILITY_LABELS = {
    icu: "ICU", oxygen: "Oxygen Supply", ventilator: "Ventilator",
    emergency_surgery: "Emergency Surgery", dialysis: "Dialysis", oncology: "Oncology",
    trauma: "Trauma / Casualty", neonatal: "Neonatal / NICU", blood_bank: "Blood Bank",
  };
  const labelFor = (cap) => CAPABILITY_LABELS[cap] ||
    cap.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());

  let capabilitySelect, stateSelect, searchBtn, countEl, errorBanner;
  let statesList = [];
  let initialized = false;
  let requestSeq = 0;

  function showError(err) {
    errorBanner.textContent = err.message || String(err);
    errorBanner.classList.remove("hidden");
  }
  function clearError() { errorBanner.classList.add("hidden"); }

  async function loadFilters() {
    const [{ capabilities }, { regions }] = await Promise.all([
      Api.getDesertCapabilities(), Api.getRegions(),
    ]);
    capabilitySelect.innerHTML = '<option value="">Select a capability…</option>' +
      capabilities.map((c) => `<option value="${c}">${labelFor(c)}</option>`).join("");
    statesList = [...new Set(regions.map((r) => r.state))].sort();
    stateSelect.innerHTML = '<option value="">All states</option>' +
      statesList.map((s) => `<option value="${s}">${s}</option>`).join("");
  }

  async function runSearch() {
    if (!capabilitySelect.value) return;
    clearError();
    countEl.innerHTML = '<span class="spinner"></span>Loading…';
    const thisRequest = ++requestSeq;
    try {
      const result = await Api.getDesertMap(capabilitySelect.value, stateSelect.value || null);
      if (thisRequest !== requestSeq) return; // a newer search superseded this one
      DesertMap.renderDistricts(result.districts);
      countEl.textContent = `${result.plotted} of ${result.count} district × capability records plotted on the map.`;
    } catch (err) {
      if (thisRequest !== requestSeq) return;
      countEl.textContent = "";
      showError(err);
    }
  }

  function init() {
    if (initialized) return;
    initialized = true;
    capabilitySelect = document.getElementById("desert-capability-select");
    stateSelect = document.getElementById("desert-state-select");
    searchBtn = document.getElementById("desert-search-btn");
    countEl = document.getElementById("desert-count");
    errorBanner = document.getElementById("desert-error-banner");

    capabilitySelect.addEventListener("change", () => {
      searchBtn.disabled = !capabilitySelect.value;
    });
    searchBtn.addEventListener("click", runSearch);

    loadFilters().catch(showError);
  }

  function onTabActivated() {
    DesertMap.invalidateSize();
  }

  return { init, onTabActivated };
})();
