// web/app/static/js/inasistencias_form.js
(function () {
  "use strict";

  document.addEventListener("DOMContentLoaded", function () {
    const formNuevo = document.getElementById("form-inasistencia");
    const formEditar = document.getElementById("form-editar-inasistencia");

    if (formNuevo) initNuevo(formNuevo);
    if (formEditar) initEditar(formEditar);
  });

  function byId(id) {
    return document.getElementById(id);
  }

  function toggleHoras(options) {
    const tipo = byId("tipo");
    const box = byId("box-horas");
    const hhmm = byId("hhmm");
    const err = byId("hhmm_error");
    if (!tipo || !box) return;

    const esHoras = tipo.value === "HORAS";
    box.style.display = esHoras ? "block" : "none";

    if (hhmm && options && options.requireHoras) hhmm.required = esHoras;
    if (!esHoras && err) err.style.display = "none";
  }

  function toggleMotivoGroups() {
    const tipo = byId("tipo");
    const grpDia = byId("grp-dia");
    const grpHoras = byId("grp-horas");
    if (!tipo || !grpDia || !grpHoras) return;

    grpDia.hidden = tipo.value !== "DIA";
    grpHoras.hidden = tipo.value !== "HORAS";
  }

  function forceMotivoMatchTipo(allowAmbos) {
    const tipo = byId("tipo");
    const sel = byId("motivo");
    const err = byId("motivo_tipo_error");
    if (!tipo || !sel) return true;

    toggleMotivoGroups();

    const opt = sel.options[sel.selectedIndex];
    const optTipo = opt ? (opt.getAttribute("data-tipo") || "").toUpperCase() : "";

    if (allowAmbos && optTipo === "AMBOS") {
      if (err) err.style.display = "none";
      return true;
    }

    if (optTipo && optTipo === tipo.value) {
      if (err) err.style.display = "none";
      return true;
    }

    for (let i = 0; i < sel.options.length; i += 1) {
      const option = sel.options[i];
      const optionTipo = (option.getAttribute("data-tipo") || "").toUpperCase();
      if (optionTipo === tipo.value) {
        sel.selectedIndex = i;
        break;
      }
    }

    if (err) err.style.display = "none";
    return true;
  }

  function updateMotivoInfo() {
    const sel = byId("motivo");
    if (!sel) return;

    const opt = sel.options[sel.selectedIndex];
    const noDesc = opt && opt.getAttribute("data-no-descuenta") === "1";
    const val = sel.value;

    const boxNoDesc = byId("info_no_descuenta");
    const boxDuelo = byId("info_duelo");

    if (boxNoDesc) boxNoDesc.style.display = noDesc ? "block" : "none";
    if (boxDuelo) boxDuelo.style.display = val === "PERMISO_DUELO" ? "block" : "none";
  }

  function extractIdFromOptionValue(value) {
    const match = (value || "").match(/^(\d+)\s*-\s*/);
    return match ? match[1] : "";
  }

  function syncHiddenTrabajadorId() {
    const input = byId("trabajador_search");
    const hidden = byId("trabajador_id");
    const err = byId("trabajador_error");
    if (!input || !hidden) return;

    const id = extractIdFromOptionValue(input.value);
    hidden.value = id;
    if (err) err.style.display = id ? "none" : "block";
  }

  function validateTrabajadorSelected(event) {
    const hidden = byId("trabajador_id");
    const err = byId("trabajador_error");
    const input = byId("trabajador_search");

    if (hidden && !hidden.value) {
      event.preventDefault();
      if (err) err.style.display = "block";
      if (input) input.focus();
      return false;
    }
    return true;
  }

  function validateMotivoTipo(event, allowAmbos) {
    const tipo = byId("tipo");
    const sel = byId("motivo");
    const err = byId("motivo_tipo_error");
    if (!tipo || !sel) return true;

    const opt = sel.options[sel.selectedIndex];
    const optTipo = opt ? (opt.getAttribute("data-tipo") || "").toUpperCase() : "";

    if (allowAmbos && optTipo === "AMBOS") {
      if (err) err.style.display = "none";
      return true;
    }

    if (!optTipo || optTipo !== tipo.value) {
      forceMotivoMatchTipo(allowAmbos);
      const opt2 = sel.options[sel.selectedIndex];
      const optTipo2 = opt2 ? (opt2.getAttribute("data-tipo") || "").toUpperCase() : "";

      if (!(allowAmbos && optTipo2 === "AMBOS") && (!optTipo2 || optTipo2 !== tipo.value)) {
        event.preventDefault();
        if (err) err.style.display = "block";
        sel.focus();
        return false;
      }
    }

    if (err) err.style.display = "none";
    return true;
  }

  function validateHoras(event) {
    const tipo = byId("tipo");
    const hhmm = byId("hhmm");
    const err = byId("hhmm_error");

    if (tipo && tipo.value === "HORAS") {
      const value = hhmm ? (hhmm.value || "").trim() : "";
      if (!value || value === "00:00") {
        event.preventDefault();
        if (err) err.style.display = "block";
        if (hhmm) hhmm.focus();
        return false;
      }
      if (err) err.style.display = "none";
    }
    return true;
  }

  function initNuevo(form) {
    const tipo = byId("tipo");
    const input = byId("trabajador_search");
    const motivo = byId("motivo");

    function refresh() {
      toggleHoras({ requireHoras: false });
      forceMotivoMatchTipo(false);
      updateMotivoInfo();
    }

    refresh();

    if (tipo) tipo.addEventListener("change", refresh);
    if (input) {
      input.addEventListener("input", syncHiddenTrabajadorId);
      input.addEventListener("change", syncHiddenTrabajadorId);
    }
    if (motivo) motivo.addEventListener("change", function () {
      forceMotivoMatchTipo(false);
      updateMotivoInfo();
    });

    form.addEventListener("submit", function (event) {
      if (!validateTrabajadorSelected(event)) return;
      validateMotivoTipo(event, false);
    });

    syncHiddenTrabajadorId();
  }

  function initEditar(form) {
    const tipo = byId("tipo");
    const motivo = byId("motivo");

    function refresh() {
      toggleHoras({ requireHoras: true });
      forceMotivoMatchTipo(true);
      updateMotivoInfo();
    }

    refresh();

    if (tipo) tipo.addEventListener("change", refresh);
    if (motivo) motivo.addEventListener("change", function () {
      forceMotivoMatchTipo(true);
      updateMotivoInfo();
    });

    form.addEventListener("submit", function (event) {
      validateHoras(event);
      validateMotivoTipo(event, true);
    });
  }
})();
