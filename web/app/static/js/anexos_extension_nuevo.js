(function () {
  const fechaAnexo = document.getElementById("fecha_anexo");
  const fechaNueva = document.getElementById("fecha_termino_nueva");
  const fechaAnteriorISO = document.getElementById("fecha_termino_anterior_iso")?.value || "";
  const form = document.getElementById("form-anexo-extension");
  const btn = document.getElementById("btn-submit");
  const err = document.getElementById("error-fecha-nueva");

  const todayISO = new Date().toISOString().slice(0, 10);
  if (fechaAnexo && !fechaAnexo.value) fechaAnexo.value = todayISO;

  function addDaysISO(iso, days) {
    const d = new Date(iso + "T00:00:00");
    d.setDate(d.getDate() + days);
    return d.toISOString().slice(0, 10);
  }

  if (fechaAnteriorISO && fechaNueva) {
    fechaNueva.min = addDaysISO(fechaAnteriorISO, 1);
  }

  function validateFechaNueva() {
    if (!fechaNueva) return true;
    if (!fechaAnteriorISO) return true;
    if (!fechaNueva.value) return false;

    const ok = fechaNueva.value > fechaAnteriorISO;
    fechaNueva.classList.toggle("is-invalid", !ok);
    if (err) err.classList.toggle("d-block", !ok);

    return ok;
  }

  if (fechaNueva) {
    fechaNueva.addEventListener("change", validateFechaNueva);
    fechaNueva.addEventListener("blur", validateFechaNueva);
  }

  if (form) {
    form.addEventListener("submit", function (event) {
      if (form.dataset.submitted === "1") {
        event.preventDefault();
        event.stopPropagation();
        return;
      }

      if (!validateFechaNueva()) {
        event.preventDefault();
        event.stopPropagation();
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
