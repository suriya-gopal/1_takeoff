/* Draws every dashboard chart from /dashboard/charts.json: one shared list of request rows, one definition per chart. */
(function () {
  "use strict";

  var script = document.currentScript;
  var options = {
    actions: { export: true, source: false, compiled: false, editor: false },
    renderer: "svg",
    config: {
      font: "system-ui, -apple-system, 'Segoe UI', Roboto, Arial, sans-serif",
      axis: { labelColor: "#16233b", titleColor: "#5b6b85", gridColor: "#e6edf6" },
      legend: { labelColor: "#16233b", titleColor: "#5b6b85" },
      range: { category: ["#1f3a68", "#4a78a8", "#3f8f87", "#b8975a", "#6b7a90", "#7d6b91", "#a3684f"] }
    }
  };

  function showError(el, text) {
    el.innerHTML = '<p class="empty-note">' + text + "</p>";
  }

  fetch(script.getAttribute("data-charts-url"), { credentials: "same-origin" })
    .then(function (response) {
      if (!response.ok) { throw new Error("HTTP " + response.status); }
      return response.json();
    })
    .then(function (payload) {
      document.querySelectorAll("[data-dash-chart]").forEach(function (el) {
        var spec = payload.charts[el.getAttribute("data-dash-chart")];
        if (!spec) { showError(el, "This chart is not available."); return; }
        spec.datasets = { rows: payload.rows };
        vegaEmbed(el, spec, options).catch(function () { showError(el, "This chart could not be drawn."); });
      });
    })
    .catch(function () {
      document.querySelectorAll("[data-dash-chart]").forEach(function (el) {
        showError(el, "The chart data could not be loaded right now.");
      });
    });
})();
