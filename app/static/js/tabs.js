(() => {
  const tabButtons = document.querySelectorAll("#app-tabs button");
  const sections = document.querySelectorAll(".view-section");

  // Views with their own Leaflet map register an onTabActivated hook here
  // (e.g. to call invalidateSize()) — a map sized inside a hidden container
  // renders broken tiles, so each map-bearing view handles this itself.
  // NOTE: DesertApp/ReadinessDesk are declared with `const` in their own
  // <script> files — that creates a global binding visible here as a bare
  // identifier, but (unlike `var`) it is NOT a property of `window`. Guard
  // with `typeof` against the bare name, not `window.X`.
  const onActivateHooks = {
    desert: () => typeof DesertApp !== "undefined" && DesertApp.onTabActivated && DesertApp.onTabActivated(),
  };

  function activate(view) {
    tabButtons.forEach((btn) => {
      const isActive = btn.dataset.view === view;
      btn.classList.toggle("active", isActive);
      btn.setAttribute("aria-selected", String(isActive));
    });
    sections.forEach((sec) => sec.classList.toggle("hidden", sec.dataset.view !== view));
    if (onActivateHooks[view]) onActivateHooks[view]();
  }

  tabButtons.forEach((btn) => {
    btn.addEventListener("click", () => activate(btn.dataset.view));
  });

  document.addEventListener("DOMContentLoaded", () => {
    if (typeof DesertApp !== "undefined" && DesertApp.init) DesertApp.init();
    if (typeof ReadinessDesk !== "undefined" && ReadinessDesk.init) ReadinessDesk.init();
  });
})();
