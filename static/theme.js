// Loaded in <head> so a saved light/dark choice applies before first paint.
// Without a saved choice the page follows the system setting.
(function () {
  try {
    var theme = localStorage.getItem("theme");
    if (theme === "light" || theme === "dark") document.documentElement.dataset.theme = theme;
  } catch (err) {
    /* storage unavailable: follow the system */
  }
})();
