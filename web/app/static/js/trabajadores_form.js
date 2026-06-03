// web/app/static/js/trabajadores_form.js
(function () {
  "use strict";

  document.addEventListener("DOMContentLoaded", function () {
    initSubmitAction();
    initCargoSearch();
    initCuentaRut();
    initPagoTercero();
  });

  function initSubmitAction() {
    const form = document.getElementById("form-nuevo-trabajador");
    const accionHidden = document.getElementById("accion");
    if (!form || !accionHidden) return;

    form.addEventListener("click", function (event) {
      const btn = event.target.closest("button[type='submit'][data-accion]");
      if (!btn) return;
      accionHidden.value = btn.getAttribute("data-accion") || "guardar";
    });

    form.addEventListener("submit", function (event) {
      const submitter = event.submitter;
      if (submitter && submitter.dataset && submitter.dataset.accion) {
        accionHidden.value = submitter.dataset.accion;
      }
      if (!accionHidden.value) accionHidden.value = "guardar";
    });
  }

  function initCargoSearch() {
    const inputCargo = document.getElementById("cargo_search");
    const hiddenCargo = document.getElementById("cargo_id");
    const datalist = document.getElementById("lista_cargos");
    const cargoError = document.getElementById("cargo_error");

    if (!inputCargo || !hiddenCargo || !datalist) return;

    function sincronizarCargoId() {
      const valor = inputCargo.value.trim();
      if (!valor) {
        hiddenCargo.value = "";
        if (cargoError) cargoError.style.display = "none";
        return;
      }

      const opciones = Array.from(datalist.options);
      const encontrada = opciones.find(function (option) { return option.value === valor; });

      if (encontrada) {
        hiddenCargo.value = encontrada.getAttribute("data-id") || "";
        if (cargoError) cargoError.style.display = "none";
      } else {
        hiddenCargo.value = "";
        if (cargoError) cargoError.style.display = "block";
      }
    }

    inputCargo.addEventListener("change", sincronizarCargoId);
    inputCargo.addEventListener("blur", sincronizarCargoId);
    sincronizarCargoId();
  }

  function initCuentaRut() {
    const rutInput = document.getElementById("rut");
    const tipoCuentaSel = document.getElementById("tipo_cuenta");
    const cuentaNumInp = document.getElementById("cuenta_numero");

    if (!rutInput || !tipoCuentaSel || !cuentaNumInp) return;

    function actualizarCuentaRut() {
      if (tipoCuentaSel.value === "CTA_RUT") {
        const rut = rutInput.value || "";
        const soloDigitos = rut.replace(/[^0-9]/g, "");
        if (soloDigitos.length >= 2) {
          cuentaNumInp.value = soloDigitos.slice(0, -1);
        }
        cuentaNumInp.readOnly = true;
      } else {
        cuentaNumInp.readOnly = false;
      }
    }

    tipoCuentaSel.addEventListener("change", actualizarCuentaRut);
    rutInput.addEventListener("blur", function () {
      if (tipoCuentaSel.value === "CTA_RUT") actualizarCuentaRut();
    });

    actualizarCuentaRut();
  }

  function initPagoTercero() {
    const chkTercero = document.getElementById("pago_tercero_activo");
    const bloqueTercero = document.getElementById("bloque_pago_tercero");

    if (!chkTercero || !bloqueTercero) return;

    const inputsTercero = bloqueTercero.querySelectorAll("input, select");

    function actualizarBloqueTercero() {
      if (chkTercero.checked) {
        bloqueTercero.style.display = "";
      } else {
        bloqueTercero.style.display = "none";
        inputsTercero.forEach(function (el) { el.value = ""; });
      }
    }

    chkTercero.addEventListener("change", actualizarBloqueTercero);
    actualizarBloqueTercero();
  }
})();
