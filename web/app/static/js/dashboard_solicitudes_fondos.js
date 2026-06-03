(function () {
  function initProgressBars() {
    document.querySelectorAll(".js-progress-width").forEach(function (el) {
      const width = Number(el.dataset.width || 0);
      el.style.width = width.toFixed(2) + "%";
    });
  }

  function parseJsonScript(id, fallback) {
    const raw = document.getElementById(id);
    if (!raw) return fallback;

    try {
      return JSON.parse(raw.textContent || "[]");
    } catch (err) {
      console.error("No se pudo parsear " + id + ":", err);
      return fallback;
    }
  }

  function initChartEvolucion() {
    const canvas = document.getElementById("chartEvolucionSolicitudes");
    if (!canvas || typeof Chart === "undefined") return;

    const serieRango = parseJsonScript("serie-rango-data", []);
    if (!serieRango.length) return;

    const labels = serieRango.map(function (row) { return row.periodo; });
    const dataTotal = serieRango.map(function (row) { return Number(row.TOTAL || 0); });
    const dataRemu = serieRango.map(function (row) { return Number(row.REMU || 0); });
    const dataRend = serieRango.map(function (row) { return Number(row.REND || 0); });
    const dataTerc = serieRango.map(function (row) { return Number(row.TERC || 0); });
    const dataVar = serieRango.map(function (row) { return Number(row.VAR || 0); });

    new Chart(canvas, {
      type: "line",
      data: {
        labels: labels,
        datasets: [
          { label: "Total", data: dataTotal, borderWidth: 3, tension: 0.28, fill: false },
          { label: "REMU", data: dataRemu, borderWidth: 2, tension: 0.25, fill: false },
          { label: "REND", data: dataRend, borderWidth: 2, tension: 0.25, fill: false },
          { label: "TERC", data: dataTerc, borderWidth: 2, tension: 0.25, fill: false },
          { label: "VAR", data: dataVar, borderWidth: 2, tension: 0.25, fill: false }
        ]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        interaction: { mode: "index", intersect: false },
        plugins: {
          legend: { position: "top" },
          tooltip: {
            callbacks: {
              label: function (context) {
                const value = Number(context.parsed.y || 0);
                return context.dataset.label + ": $" + value.toLocaleString("es-CL");
              }
            }
          }
        },
        scales: {
          y: {
            beginAtZero: true,
            ticks: {
              callback: function (value) {
                return "$" + Number(value).toLocaleString("es-CL");
              }
            }
          }
        }
      }
    });
  }

  document.addEventListener("DOMContentLoaded", function () {
    initProgressBars();
    initChartEvolucion();
  });
})();
