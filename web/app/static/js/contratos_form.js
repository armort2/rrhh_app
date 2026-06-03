// web/app/static/js/contratos_form.js
(function () {
  "use strict";

  document.addEventListener("DOMContentLoaded", function () {
    initHorarioPreview();
    initHorasSemanalesDefault();
  });

  function initHorarioPreview() {
    const selHorario = document.getElementById("horario_id");
    const wrap = document.getElementById("horario_preview_wrap");
    const box = document.getElementById("horario_preview");

    if (!selHorario || !wrap || !box) return;

    function refreshHorarioPreview() {
      const opt = selHorario.options[selHorario.selectedIndex];
      const desc = opt && opt.dataset ? (opt.dataset.desc || "") : "";

      if (desc.trim()) {
        box.textContent = desc;
        wrap.style.display = "block";
        wrap.classList.remove("d-none");
      } else {
        box.textContent = "";
        wrap.style.display = "none";
        wrap.classList.add("d-none");
      }
    }

    selHorario.addEventListener("change", refreshHorarioPreview);
    refreshHorarioPreview();
  }

  function initHorasSemanalesDefault() {
    const selTipo = document.getElementById("tipo_contrato");
    const inpHoras = document.getElementById("horas_semanales");

    if (!selTipo || !inpHoras) return;

    function defaultHorasPorTipo(tipo) {
      const map = {
        PART_TIME: 18,
        INDEFINIDO: 44,
        PLAZO_FIJO: 44,
        FAENA: 44
      };
      return map[tipo] || "";
    }

    function refreshHoras() {
      const tipo = (selTipo.value || "").trim();
      const current = (inpHoras.value || "").trim();

      if (!current) {
        const def = defaultHorasPorTipo(tipo);
        if (def) inpHoras.value = String(def);
      }
    }

    selTipo.addEventListener("change", refreshHoras);
    refreshHoras();
  }
})();
