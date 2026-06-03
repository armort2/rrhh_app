document.addEventListener("DOMContentLoaded", function () {
  const formGenerar = document.getElementById("form-generar-anexos");
  const btnGenerar = document.getElementById("btn-generar-anexos");
  const msgGenerando = document.getElementById("msg-generando-anexos");
  const progresoGeneracion = document.getElementById("progreso-generacion-ui");
  const btnAplicar = document.getElementById("btn-aplicar-cambios");
  const btnGuardarSeleccion = document.getElementById("btn-guardar-seleccion");
  const btnGuardarSeleccionFooter = document.getElementById("btn-guardar-seleccion-footer");

  if (!formGenerar || !btnGenerar) return;

  formGenerar.addEventListener("submit", function () {
    btnGenerar.disabled = true;
    btnGenerar.classList.add("disabled");

    const normal = btnGenerar.querySelector(".label-normal");
    const loading = btnGenerar.querySelector(".label-loading");

    if (normal) normal.classList.add("d-none");
    if (loading) loading.classList.remove("d-none");
    if (msgGenerando) msgGenerando.classList.remove("d-none");
    if (progresoGeneracion) progresoGeneracion.classList.remove("d-none");

    [btnAplicar, btnGuardarSeleccion, btnGuardarSeleccionFooter].forEach((btn) => {
      if (!btn) return;
      btn.disabled = true;
      btn.classList.add("disabled");
    });

    if (btnAplicar) btnAplicar.classList.add("d-none");
  });
});
