(function () {
  function readJson(id, fallback) {
    const el = document.getElementById(id);
    if (!el) return fallback;

    try {
      return JSON.parse(el.textContent || "null") ?? fallback;
    } catch (err) {
      console.error("No se pudo leer " + id + ":", err);
      return fallback;
    }
  }

  function buildTSV(rows, meta) {
    const lines = [];
    const titulo = `Dashboard · Dotación Mensual · ${String(meta.month).padStart(2, "0")}/${meta.year} · Rango: ${meta.inicio} → ${meta.fin}`;

    lines.push(titulo);
    lines.push("");
    lines.push(["Obra", "Directos", "Indirectos", "Total"].join("\t"));

    for (const r of rows) {
      lines.push([r.obra ?? "", r.directos ?? 0, r.indirectos ?? 0, r.total ?? 0].join("\t"));
    }

    lines.push("");
    lines.push(["TOTAL", meta.total_directos, meta.total_indirectos, meta.total_total].join("\t"));

    return lines.join("\n");
  }

  async function copyText(text) {
    if (navigator.clipboard && window.isSecureContext) {
      await navigator.clipboard.writeText(text);
      return;
    }

    const ta = document.createElement("textarea");
    ta.value = text;
    ta.setAttribute("readonly", "");
    ta.style.position = "fixed";
    ta.style.top = "-9999px";
    document.body.appendChild(ta);
    ta.select();
    document.execCommand("copy");
    document.body.removeChild(ta);
  }

  function initCopyButton(rows, meta) {
    const btnCopy = document.getElementById("btnCopyTabla1");
    if (!btnCopy) return;

    btnCopy.addEventListener("click", async () => {
      try {
        const tsv = buildTSV(rows, meta);
        await copyText(tsv);

        btnCopy.classList.remove("btn-outline-secondary");
        btnCopy.classList.add("btn-success");
        const prevHtml = btnCopy.innerHTML;
        btnCopy.innerHTML = '<i class="bi bi-check2"></i> Copiado';

        setTimeout(() => {
          btnCopy.classList.remove("btn-success");
          btnCopy.classList.add("btn-outline-secondary");
          btnCopy.innerHTML = prevHtml;
        }, 1200);
      } catch (e) {
        console.error(e);
        alert("No se pudo copiar la tabla. Intenta nuevamente.");
      }
    });
  }

  function initTrendChart(trend) {
    const tc = document.getElementById("trendChart");
    if (!tc || typeof Chart === "undefined") return;

    new Chart(tc, {
      type: "line",
      data: {
        labels: trend.map((x) => x.label),
        datasets: [
          { label: "Total", data: trend.map((x) => x.total), tension: 0.25 },
          { label: "Directos", data: trend.map((x) => x.directos), tension: 0.25 },
          { label: "Indirectos", data: trend.map((x) => x.indirectos), tension: 0.25 }
        ]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        interaction: { mode: "index", intersect: false },
        plugins: { legend: { display: true } },
        scales: { y: { beginAtZero: true } }
      }
    });
  }

  function initEmpresasChart(topEmpresas) {
    const ec = document.getElementById("empresasChart");
    if (!ec || typeof Chart === "undefined") return;

    new Chart(ec, {
      type: "bar",
      data: {
        labels: topEmpresas.map((x) => x.empresa),
        datasets: [{ label: "Contratos (Top 8)", data: topEmpresas.map((x) => x.total) }]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: { legend: { display: false } },
        scales: {
          x: { ticks: { maxRotation: 45, minRotation: 0 } },
          y: { beginAtZero: true }
        }
      }
    });
  }

  function initCaretQuintero() {
    const btn = document.querySelector('[data-bs-target="#grp-quintero"]');
    const grp = document.getElementById("grp-quintero");
    if (!btn || !grp) return;

    const ico = btn.querySelector("i.bi");
    if (!ico) return;

    grp.addEventListener("show.bs.collapse", () => {
      ico.classList.remove("bi-caret-right-fill");
      ico.classList.add("bi-caret-down-fill");
    });

    grp.addEventListener("hide.bs.collapse", () => {
      ico.classList.remove("bi-caret-down-fill");
      ico.classList.add("bi-caret-right-fill");
    });
  }

  document.addEventListener("DOMContentLoaded", function () {
    const rows = readJson("personal-mes-copiar-rows", []);
    const meta = readJson("personal-mes-meta", {});
    const trend = readJson("personal-mes-trend-12m", []);
    const topEmpresas = readJson("personal-mes-top-empresas", []);

    initCopyButton(rows, meta);
    initTrendChart(trend);
    initEmpresasChart(topEmpresas);
    initCaretQuintero();
  });
})();
