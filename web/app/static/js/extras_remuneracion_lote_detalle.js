(function () {
  function parseNum(val) {
    return (val || "").toString().replace(/\./g, "").replace(/,/g, ".").trim();
  }

  function initNuevoItemForm() {
    const concepto = document.getElementById("conceptoSelect");
    const bonoWrap = document.getElementById("codigoBonoWrap");
    const bonoSel = document.getElementById("codigoBonoSelect");
    const tratoWrap = document.getElementById("tratoWrap");
    const uInp = document.getElementById("tratoUnidades");
    const vInp = document.getElementById("tratoValor");
    const montoInp = document.getElementById("montoInput");
    const montoHelp = document.getElementById("montoHelp");

    function calcTrato() {
      if (!uInp || !vInp || !montoInp) return;
      const u = parseFloat(parseNum(uInp.value)) || 0;
      const v = parseFloat(parseNum(vInp.value)) || 0;
      const m = Math.round(u * v);
      montoInp.value = m > 0 ? String(m) : "";
    }

    function sync() {
      const val = concepto ? concepto.value : "";
      const isBono = val === "BONO";
      const isTrato = val === "TRATO";

      if (bonoWrap && bonoSel) {
        if (isBono) {
          bonoWrap.style.display = "";
          bonoSel.setAttribute("required", "required");
        } else {
          bonoWrap.style.display = "none";
          bonoSel.removeAttribute("required");
          bonoSel.value = "";
        }
      }

      if (tratoWrap && uInp && vInp) {
        if (isTrato) {
          tratoWrap.style.display = "";
          uInp.setAttribute("required", "required");
          vInp.setAttribute("required", "required");
        } else {
          tratoWrap.style.display = "none";
          uInp.removeAttribute("required");
          vInp.removeAttribute("required");
          uInp.value = "";
          vInp.value = "";
        }
      }

      if (montoInp) {
        if (isTrato) {
          montoInp.setAttribute("readonly", "readonly");
          if (montoHelp) montoHelp.style.display = "";
          calcTrato();
        } else {
          montoInp.removeAttribute("readonly");
          if (montoHelp) montoHelp.style.display = "none";
        }
      }
    }

    if (concepto) concepto.addEventListener("change", sync);
    if (uInp) uInp.addEventListener("input", calcTrato);
    if (vInp) vInp.addEventListener("input", calcTrato);
    sync();
  }

  function calcTratoInContainer(container) {
    if (!container) return;

    const u = container.querySelector('input[name="unidades"]');
    const v = container.querySelector('input[name="valor_unidad"]');
    const m = container.querySelector('input[name="monto"]');

    if (!u || !v || !m) return;

    const uu = parseFloat(parseNum(u.value)) || 0;
    const vv = parseFloat(parseNum(v.value)) || 0;
    const mm = Math.round(uu * vv);

    m.value = mm > 0 ? String(mm) : "0";
  }

  initNuevoItemForm();

  document.addEventListener("input", function (ev) {
    const t = ev.target;
    if (!t) return;

    if (t.name === "unidades" || t.name === "valor_unidad") {
      const modal = t.closest(".modal");
      if (modal) calcTratoInContainer(modal);
    }
  });

  document.addEventListener("shown.bs.modal", function (ev) {
    const modal = ev.target;
    if (modal && modal.classList && modal.classList.contains("modal")) {
      calcTratoInContainer(modal);
    }
  });
})();
