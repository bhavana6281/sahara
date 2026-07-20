const DesertMap = (() => {
  // Deliberately a different hue family from the trust-level colors
  // (green/amber/red) so the two legends are never visually confused —
  // validated with the dataviz skill's color-formula method, not eyeballed.
  const COLORS = { covered: "#1baf7a", medical_desert: "#4a3aa7", data_desert: "#2a78d6" };
  const LABELS = { covered: "Covered", medical_desert: "Medical desert (confirmed absent)",
                    data_desert: "Data desert (unknown, not confirmed absent)" };

  let map = null;
  let markers = [];

  function init() {
    map = L.map("desert-map").setView([22.5, 82.0], 5);
    L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
      attribution: "&copy; OpenStreetMap contributors",
      maxZoom: 18,
    }).addTo(map);
    return map;
  }

  function isReady() { return map !== null; }

  function invalidateSize() { if (map) map.invalidateSize(); }

  function clear() {
    markers.forEach((m) => map.removeLayer(m));
    markers = [];
  }

  function renderDistricts(districts) {
    if (!map) init();
    clear();
    const withCoords = districts.filter((d) => d.latitude != null && d.longitude != null);
    withCoords.forEach((d) => {
      const color = COLORS[d.status] || "#888";
      const marker = L.circleMarker([d.latitude, d.longitude], {
        radius: 7, color, fillColor: color, fillOpacity: 0.8, weight: 2,
      }).addTo(map);
      marker.bindPopup(
        `<strong>${d.district}, ${d.state}</strong><br/>` +
        `${LABELS[d.status] || d.status}<br/>` +
        `${d.n_present}/${d.n_facilities} facilities confirmed present ` +
        `(coverage ${Math.round(d.coverage_ratio * 100)}%)<br/>` +
        `<em>Approximate location — centroid of ${d.n_geolocated_facilities} facility record(s), not a district boundary.</em>`
      );
      markers.push(marker);
    });
    if (withCoords.length) {
      map.fitBounds(L.latLngBounds(withCoords.map((d) => [d.latitude, d.longitude])),
        { padding: [30, 30], maxZoom: 10 });
    }
    return { plotted: withCoords.length, total: districts.length };
  }

  return { init, isReady, invalidateSize, renderDistricts };
})();
