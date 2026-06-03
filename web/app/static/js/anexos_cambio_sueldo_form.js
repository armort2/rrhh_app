(function () {
  const form = document.getElementById("form-anexo-cambio-sueldo");
  const btn = document.getElementById("btn-submit");
  const fechaCambio = document.getElementById("fecha_cambio");

  const actual = {
    sueldo: Number(form?.dataset.sueldoActual || 0),
    colacion: Number(form?.dataset.colacionActual || 0),
    movilizacion: Number(form?.dataset.movilizacionActual || 0),
  };

  const inputs = {
    sueldo: document.getElementById("sueldo_base_nuevo"),
    colacion: document.getElementById("asignacion_colacion_nueva"),
    movilizacion: document.getElementById("asignacion_movilizacion_nueva"),
  };

  const diffs = {
    sueldo: document.getElementById("diff-sueldo"),
    colacion: document.getElementById("diff-colacion"),
    movilizacion: document.getElementById("diff-movilizacion"),
  };

  const todayISO = new Date().toISOString().slice(0, 10);
  if (fechaCambio && !fechaCambio.value) fechaCambio.value = todayISO;

  function parseMoney(value) {
    const raw = String(value || "").replace(/\$/g, "").replace(/\s/g, "").replace(/\./g, "").replace(/,/g, ".");
    const n = Number(raw);
    return Number.isFinite(n) && n >= 0 ? Math.round(n) : null;
  }

  function fmtCLP(n) {
    const sign = n < 0 ? "-" : "";
    return sign + "$ " + Math.abs(Math.round(n)).toLocaleString("es-CL");
  }

  function validateInput(input) {
    const ok = parseMoney(input.value) !== null;
    input.classList.toggle("is-invalid", !ok);
    return ok;
  }

  function refreshDiff(key) {
    const value = parseMoney(inputs[key].value);
    if (value === null) {
      diffs[key].textContent = "—";
      return;
    }
    diffs[key].textContent = fmtCLP(value - actual[key]);
  }

  Object.keys(inputs).forEach(function (key) {
    inputs[key].addEventListener("input", function () {
      validateInput(inputs[key]);
      refreshDiff(key);
    });
    refreshDiff(key);
  });

  if (form) {
    form.addEventListener("submit", function (e) {
      if (form.dataset.submitted === "1") {
        e.preventDefault();
        e.stopPropagation();
        return;
      }

      let ok = true;
      Object.keys(inputs).forEach(function (key) {
        if (!validateInput(inputs[key])) ok = false;
      });

      if (!ok) {
        e.preventDefault();
        e.stopPropagation();
        return;
      }

      form.dataset.submitted = "1";
      if (btn) {
        btn.disabled = true;
        btn.textContent = "Generando…";
      }
    });
  }
})();
