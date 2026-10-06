/* Draws every chart on the page from the definition named in its data-chart-spec attribute. */
(function () {
  "use strict";

  var options = {
    actions: { export: true, source: false, compiled: false, editor: false },
    renderer: "svg"
  };

  document.querySelectorAll("[data-chart-spec]").forEach(function (el) {
    vegaEmbed(el, el.getAttribute("data-chart-spec"), options).catch(function () {
      el.innerHTML = '<p class="empty-note">This chart could not be loaded right now.</p>';
    });
  });

  // Show each data feed as a full address, ready to paste into a charting tool.
  document.querySelectorAll("[data-feed-url]").forEach(function (el) {
    el.textContent = new URL(el.getAttribute("href"), window.location.href).href;
  });
})();
