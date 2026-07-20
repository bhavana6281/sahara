const Api = (() => {
  async function request(path) {
    const res = await fetch(path, { headers: { "Accept": "application/json" } });
    if (!res.ok) {
      const body = await res.json().catch(() => ({}));
      throw new Error(body.detail || `Request failed (${res.status})`);
    }
    return res.json();
  }

  async function requestJson(path, method, payload) {
    const res = await fetch(path, {
      method,
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    if (!res.ok) {
      const body = await res.json().catch(() => ({}));
      throw new Error(body.detail || `Request failed (${res.status})`);
    }
    return res.json();
  }

  return {
    getMeta: () => request("/api/meta"),
    getCapabilities: () => request("/api/capabilities"),
    getRegions: () => request("/api/regions"),
    searchFacilities: (capability, state, district, limit = 60) => {
      const params = new URLSearchParams({ capability, state, limit });
      if (district) params.set("district", district);
      return request(`/api/facilities?${params.toString()}`);
    },
    getFacilityDetail: (uniqueId) => request(`/api/facilities/${encodeURIComponent(uniqueId)}`),
    getActions: (uniqueId) => request(`/api/facilities/${encodeURIComponent(uniqueId)}/actions`),
    addAction: (uniqueId, payload) =>
      requestJson(`/api/facilities/${encodeURIComponent(uniqueId)}/actions`, "POST", payload),
    nlQuery: (question) => requestJson("/api/query", "POST", { question }),
    getDesertCapabilities: () => request("/api/desert/capabilities"),
    getDesertMap: (capability, state) => {
      const params = new URLSearchParams({ capability });
      if (state) params.set("state", state);
      return request(`/api/desert/map?${params.toString()}`);
    },
    getReadinessSummary: () => request("/api/readiness/summary"),
    getReadinessQueue: (reviewed = "all", limit = 200) => {
      const params = new URLSearchParams({ reviewed, limit });
      return request(`/api/readiness/queue?${params.toString()}`);
    },
    getReviewDecisions: (uniqueId) =>
      request(`/api/readiness/queue/${encodeURIComponent(uniqueId)}/decisions`),
    addReviewDecision: (uniqueId, payload) =>
      requestJson(`/api/readiness/queue/${encodeURIComponent(uniqueId)}/decisions`, "POST", payload),
    getArchitectureStatus: () => request("/api/architecture/status"),
  };
})();
