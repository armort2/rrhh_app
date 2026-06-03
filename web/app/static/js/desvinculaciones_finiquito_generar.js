(function () {
  const moneyFieldsIngresos = [
    "FINIQUITO_FERIADO_PROPORCIONAL",
    "FINIQUITO_AVISO_PREVIO",
    "FINIQUITO_ANIOS_SERVICIOS",
    "FINIQUITO_INDEM_VOLUNTARIA",
    "FINIQUITO_MONTO_OTROS"
  ];

  const moneyFieldsDescuentos = [
    "FINIQUITO_APORTE_EMP_SEG_CES",
    "FINIQUITO_MONTO_DESCTO_1",
    "FINIQUITO_MONTO_DESCTO_2"
  ];

  function parseMoney(str) {
    if (!str) return 0;
    const digits = String(str).replace(/[^\d]/g, "");
    return digits ? parseInt(digits, 10) : 0;
  }

  function formatCLP(n) {
    try {
      return new Intl.NumberFormat("es-CL", { maximumFractionDigits: 0 }).format(n);
    } catch (e) {
      return String(n).replace(/\B(?=(\d{3})+(?!\d))/g, ".");
    }
  }

  function recalcTotales() {
    const elSubtotal = document.getElementById("FINIQUITO_SUBTOTAL");
    const elTotalDesctos = document.getElementById("FINIQUITO_TOTAL_DESCTOS");
    const elTotalPago = document.getElementById("FINIQUITO_TOTAL_PAGO");

    let subtotal = 0;
    for (const id of moneyFieldsIngresos) {
      subtotal += parseMoney(document.getElementById(id)?.value);
    }

    let totalDesctos = 0;
    for (const id of moneyFieldsDescuentos) {
      totalDesctos += parseMoney(document.getElementById(id)?.value);
    }

    const totalPago = Math.max(0, subtotal - totalDesctos);

    if (elSubtotal) elSubtotal.value = subtotal ? formatCLP(subtotal) : "";
    if (elTotalDesctos) elTotalDesctos.value = totalDesctos ? formatCLP(totalDesctos) : "";
    if (elTotalPago) elTotalPago.value = (subtotal || totalDesctos) ? formatCLP(totalPago) : "";
  }

  function initTotalesManuales() {
    [...moneyFieldsIngresos, ...moneyFieldsDescuentos].forEach((id) => {
      const el = document.getElementById(id);
      if (!el) return;
      el.addEventListener("input", recalcTotales);
    });

    recalcTotales();
  }

  function initAsistenteCalculo() {
    const config = document.getElementById("finiquito-generar-config");
    const tipoRem = document.getElementById("asis_tipo_remuneracion");
    const varsWrap = document.getElementById("asis_variables_wrap");
    const estado = document.getElementById("asis_estado");
    const hiddenCalc = document.getElementById("CALCULO_FINIQUITO_JSON");

    if (!tipoRem || !estado || !hiddenCalc) return;

    const calcularUrl = config?.dataset.calcularUrl || "";
    const desvinculacionId = config?.dataset.desvinculacionId || "";
    const contratoId = config?.dataset.contratoId || "";

    const out = {
      base: document.getElementById("asis_out_base"),
      dias: document.getElementById("asis_out_dias_feriado"),
      diasCorridos: document.getElementById("asis_out_dias_corridos"),
      feriado: document.getElementById("asis_out_feriado"),
      aviso: document.getElementById("asis_out_aviso"),
      anios: document.getElementById("asis_out_anios"),
      meses: document.getElementById("asis_out_meses_indemnizables"),
      inicioCorridos: document.getElementById("asis_out_inicio_corridos"),
      finCorridos: document.getElementById("asis_out_fin_corridos"),
      finHabilesRef: document.getElementById("asis_out_fin_habiles_ref"),
      fechaBaseProp: document.getElementById("asis_out_fecha_base_prop"),
      diasTramoProp: document.getElementById("asis_out_dias_tramo_prop"),
      devengoTeorico: document.getElementById("asis_out_devengo_teorico"),
      diasUsados: document.getElementById("asis_out_dias_usados"),
      diasAjuste: document.getElementById("asis_out_dias_ajuste"),
      indemSueldoBase: document.getElementById("asis_out_indem_sueldo_base"),
      indemGratificacion: document.getElementById("asis_out_indem_gratificacion"),
      indemColacion: document.getElementById("asis_out_indem_colacion"),
      indemMovilizacion: document.getElementById("asis_out_indem_movilizacion"),
      indemVariable: document.getElementById("asis_out_indem_variable"),
      baseIndemnizacion: document.getElementById("asis_out_base_indemnizacion")
    };

    let ultimoResumen = null;
    let ultimoPayloadCompleto = null;

    function setValue(el, value) {
      if (el) el.value = value ?? "";
    }

    function toggleVars() {
      const v = tipoRem?.value || "FIJA";
      if (!varsWrap) return;
      varsWrap.classList.toggle("d-none", !(v === "VARIABLE" || v === "MIXTA"));
    }

    function setResultados(resumen) {
      if (!resumen) return;

      setValue(out.base, resumen.base_calculo || "");
      setValue(out.dias, resumen.dias_feriado_habiles || "");
      setValue(out.diasCorridos, resumen.dias_feriado_corridos || "");
      setValue(out.feriado, resumen.monto_feriado || "");
      setValue(out.aviso, resumen.aviso_previo || "");
      setValue(out.anios, resumen.anios_servicio || "");
      setValue(out.meses, resumen.meses_indemnizables ?? "");
      setValue(out.inicioCorridos, resumen.fecha_inicio_corridos || "");
      setValue(out.finCorridos, resumen.fecha_fin_corridos || "");
      setValue(out.finHabilesRef, resumen.fecha_fin_habiles_ref || "");

      setValue(out.fechaBaseProp, resumen.fecha_base_proporcional || "");
      setValue(out.diasTramoProp, resumen.dias_corridos_tramo_proporcional ?? "");
      setValue(out.devengoTeorico, resumen.feriado_devengado_teorico_habiles || "");
      setValue(out.diasUsados, resumen.feriado_dias_usados_habiles || "");
      setValue(out.diasAjuste, resumen.feriado_dias_ajuste || "");

      const indem = resumen.detalle_base_indemnizacion || {};
      setValue(out.indemSueldoBase, indem.sueldo_base || "");
      setValue(out.indemGratificacion, indem.gratificacion || "");
      setValue(out.indemColacion, indem.colacion || "");
      setValue(out.indemMovilizacion, indem.movilizacion || "");
      setValue(out.indemVariable, indem.promedio_variable || "");
      setValue(out.baseIndemnizacion, indem.total || resumen.base_indemnizacion || "");
    }

    function construirPayloadCalculo() {
      return {
        version: 1,
        generado_en: new Date().toISOString(),
        fuente: "asistente_modal_finiquito",
        desvinculacion_id: Number(desvinculacionId) || desvinculacionId,
        contrato_id: Number(contratoId) || contratoId,
        parametros: {
          tipo_remuneracion: document.getElementById("asis_tipo_remuneracion")?.value || "FIJA",
          aplicar_aviso_previo: !!document.getElementById("asis_aplicar_aviso_previo")?.checked,
          aplicar_anios_servicio: !!document.getElementById("asis_aplicar_anios_servicio")?.checked,
          incluir_colacion_base: !!document.getElementById("asis_incluir_colacion_base")?.checked,
          incluir_movilizacion_base: !!document.getElementById("asis_incluir_movilizacion_base")?.checked,
          incluir_gratificacion_base: !!document.getElementById("asis_incluir_gratificacion_base")?.checked,
          gratificacion_mensual: document.getElementById("asis_gratificacion_mensual")?.value || "",
          var_mes_1: document.getElementById("asis_var_mes_1")?.value || "",
          var_mes_2: document.getElementById("asis_var_mes_2")?.value || "",
          var_mes_3: document.getElementById("asis_var_mes_3")?.value || ""
        },
        resultado: ultimoResumen || {}
      };
    }

    async function calcularAsistente() {
      if (!calcularUrl) {
        estado.textContent = "Error: no se encontró la URL de cálculo.";
        return;
      }

      try {
        estado.textContent = "Calculando...";

        const fd = new FormData();
        fd.append("tipo_remuneracion", document.getElementById("asis_tipo_remuneracion")?.value || "FIJA");
        fd.append("aplicar_aviso_previo", document.getElementById("asis_aplicar_aviso_previo")?.checked ? "1" : "");
        fd.append("aplicar_anios_servicio", document.getElementById("asis_aplicar_anios_servicio")?.checked ? "1" : "");
        fd.append("incluir_colacion_base", document.getElementById("asis_incluir_colacion_base")?.checked ? "1" : "");
        fd.append("incluir_movilizacion_base", document.getElementById("asis_incluir_movilizacion_base")?.checked ? "1" : "");
        fd.append("incluir_gratificacion_base", document.getElementById("asis_incluir_gratificacion_base")?.checked ? "1" : "");
        fd.append("gratificacion_mensual", document.getElementById("asis_gratificacion_mensual")?.value || "");
        fd.append("var_mes_1", document.getElementById("asis_var_mes_1")?.value || "");
        fd.append("var_mes_2", document.getElementById("asis_var_mes_2")?.value || "");
        fd.append("var_mes_3", document.getElementById("asis_var_mes_3")?.value || "");

        const res = await fetch(calcularUrl, {
          method: "POST",
          body: fd,
          headers: { "X-Requested-With": "XMLHttpRequest" }
        });

        const data = await res.json();
        if (!res.ok || !data.ok) {
          throw new Error(data?.error || "No se pudo calcular.");
        }

        ultimoResumen = data.resumen || {};
        ultimoPayloadCompleto = construirPayloadCalculo();

        setResultados(ultimoResumen);
        estado.textContent = "Cálculo realizado correctamente.";
      } catch (err) {
        estado.textContent = "Error: " + (err.message || err);
      }
    }

    function usarValores() {
      if (!ultimoResumen) return;

      const dias = document.getElementById("FINIQUITO_DIAS_FERIADO_A_PAGO");
      const feriado = document.getElementById("FINIQUITO_FERIADO_PROPORCIONAL");
      const aviso = document.getElementById("FINIQUITO_AVISO_PREVIO");
      const anios = document.getElementById("FINIQUITO_ANIOS_SERVICIOS");

      if (dias) dias.value = ultimoResumen.dias_feriado_habiles || "";
      if (feriado) feriado.value = ultimoResumen.monto_feriado || "";
      if (aviso) aviso.value = ultimoResumen.aviso_previo || "";
      if (anios) anios.value = ultimoResumen.anios_servicio || "";

      if (hiddenCalc && ultimoPayloadCompleto) {
        hiddenCalc.value = JSON.stringify(ultimoPayloadCompleto);
      }

      const evt = new Event("input", { bubbles: true });
      dias?.dispatchEvent(evt);
      feriado?.dispatchEvent(evt);
      aviso?.dispatchEvent(evt);
      anios?.dispatchEvent(evt);

      estado.textContent = "Valores copiados al formulario principal y cálculo listo para guardar.";
    }

    function cargarCalculoPrevio() {
      if (!hiddenCalc || !hiddenCalc.value) return;

      try {
        const payload = JSON.parse(hiddenCalc.value);
        if (!payload || typeof payload !== "object") return;

        ultimoPayloadCompleto = payload;
        ultimoResumen = payload.resultado || null;

        if (payload.parametros) {
          const p = payload.parametros;

          if (tipoRem && p.tipo_remuneracion) tipoRem.value = p.tipo_remuneracion;

          const chkAviso = document.getElementById("asis_aplicar_aviso_previo");
          const chkAnios = document.getElementById("asis_aplicar_anios_servicio");
          const chkCol = document.getElementById("asis_incluir_colacion_base");
          const chkMov = document.getElementById("asis_incluir_movilizacion_base");
          const chkGrat = document.getElementById("asis_incluir_gratificacion_base");
          const gratMensual = document.getElementById("asis_gratificacion_mensual");

          if (chkAviso) chkAviso.checked = !!p.aplicar_aviso_previo;
          if (chkAnios) chkAnios.checked = !!p.aplicar_anios_servicio;
          if (chkCol) chkCol.checked = !!p.incluir_colacion_base;
          if (chkMov) chkMov.checked = !!p.incluir_movilizacion_base;
          if (chkGrat) chkGrat.checked = !!p.incluir_gratificacion_base;
          if (gratMensual) gratMensual.value = p.gratificacion_mensual || "";

          const v1 = document.getElementById("asis_var_mes_1");
          const v2 = document.getElementById("asis_var_mes_2");
          const v3 = document.getElementById("asis_var_mes_3");

          if (v1) v1.value = p.var_mes_1 || "";
          if (v2) v2.value = p.var_mes_2 || "";
          if (v3) v3.value = p.var_mes_3 || "";
        }

        toggleVars();
        setResultados(ultimoResumen);

        if (ultimoResumen) estado.textContent = "Se cargó un cálculo previo guardado.";
      } catch (e) {
        console.warn("No se pudo cargar cálculo previo de finiquito:", e);
      }
    }

    document.getElementById("btnCalcularAsistente")?.addEventListener("click", calcularAsistente);
    document.getElementById("btnUsarValoresAsistente")?.addEventListener("click", usarValores);

    tipoRem?.addEventListener("change", toggleVars);
    toggleVars();
    cargarCalculoPrevio();
  }

  document.addEventListener("DOMContentLoaded", function () {
    initTotalesManuales();
    initAsistenteCalculo();
  });
})();
