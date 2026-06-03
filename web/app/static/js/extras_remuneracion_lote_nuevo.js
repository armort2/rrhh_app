document.addEventListener("DOMContentLoaded", () => {
  const ccSel = document.getElementById("cc_select");
  const obraSel = document.getElementById("obra_select");
  if (!ccSel || !obraSel) return;

  const allOptions = Array.from(obraSel.querySelectorAll("option"))
    .filter((opt) => opt.value && (opt.dataset.cc || "").trim().length > 0);

  function resetObras(msg) {
    obraSel.innerHTML = "";
    const ph = document.createElement("option");
    ph.value = "";
    ph.textContent = msg;
    obraSel.appendChild(ph);
    obraSel.disabled = true;
  }

  function loadObrasForCC(cc) {
    const ccU = (cc || "").trim().toUpperCase();
    obraSel.innerHTML = "";

    const filtered = allOptions.filter((opt) => (opt.dataset.cc || "").toUpperCase() === ccU);

    const ph = document.createElement("option");
    ph.value = "";
    ph.textContent = filtered.length ? "— Selecciona —" : "— No hay obras para este CC —";
    obraSel.appendChild(ph);

    filtered.forEach((opt) => obraSel.appendChild(opt.cloneNode(true)));
    obraSel.disabled = filtered.length === 0;
  }

  resetObras("— Selecciona un Centro de Costo primero —");

  ccSel.addEventListener("change", () => {
    const cc = ccSel.value;
    if (!cc) {
      resetObras("— Selecciona un Centro de Costo primero —");
      return;
    }
    loadObrasForCC(cc);
  });
});
