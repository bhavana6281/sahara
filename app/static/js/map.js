const TrustMap = (() => {
  const COLORS = { High: "#1a7f37", Medium: "#b7791f", Low: "#c53030" };

  let map = null;
  let markers = [];

  function init() {
    map = L.map("map").setView([22.5, 82.0], 5); // rough India-wide default
    L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
      attribution: "&copy; OpenStreetMap contributors",
      maxZoom: 18,
    }).addTo(map);
    return map;
  }

  function clear() {
    markers.forEach((m) => map.removeLayer(m));
    markers = [];
  }

  function renderPins(facilities, onSelect) {
    clear();
    const withCoords = facilities.filter((f) => f.latitude != null && f.longitude != null);
    withCoords.forEach((f) => {
      const color = COLORS[f.trust_level] || "#888";
      const marker = L.circleMarker([f.latitude, f.longitude], {
        radius: 9,
        color,
        fillColor: color,
        fillOpacity: 0.85,
        weight: 2,
      }).addTo(map);
      marker.bindPopup(`<strong>${f.name}</strong><br/>Trust: ${f.trust_level} (${f.trust_score}/100)`);
      if (onSelect) marker.on("click", () => onSelect(f.unique_id));
      markers.push(marker);
    });
    if (withCoords.length) {
      const bounds = L.latLngBounds(withCoords.map((f) => [f.latitude, f.longitude]));
      map.fitBounds(bounds, { padding: [30, 30], maxZoom: 12 });
    }
  }

  function highlight(uniqueId, facilities) {
    const idx = facilities.findIndex((f) => f.unique_id === uniqueId);
    if (idx >= 0 && markers[idx]) markers[idx].openPopup();
  }

  return { init, renderPins, highlight };
})();
