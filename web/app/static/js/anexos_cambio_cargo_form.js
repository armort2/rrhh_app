(function () {
  const form = document.getElementById("form-anexo-cambio-cargo");
  const btn = document.getElementById("btn-submit");
  const fechaCambio = document.getElementById("fecha_cambio");
  const cargoSelect = document.getElementById("cargo_nuevo_id");
  const cargoActualId = Number(form?.dataset.cargoActualId || 0);

  const todayISO = new Date().toISOString().slice(0, 10);
  if (fechaCambio && !fechaCambio.value) fechaCambio.value = todayISO;

  function validateCargo() {
    const selected = Number(cargoSelect.value || 0);
    const ok = selected > 0 && selected !== cargoActualId;
    cargoSelect.classList.toggle("is-invalid", !ok);
    return ok;
  }

  if (cargoSelect) {
    cargoSelect.addEventListener("change", validateCargo);
  }

  if (form) {
    form.addEventListener("submit", function (e) {
      if (form.dataset.submitted === "1") {
        e.preventDefault();
        e.stopPropagation();
        return;
      }

      if (!validateCargo()) {
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
