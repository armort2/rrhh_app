(function () {
  const form = document.querySelector("form");
  const inputBuscar = document.getElementById("trabajador_buscar");
  const inputId = document.getElementById("trabajador_id");
  const inputContratoId = document.getElementById("contrato_id");
  const suggestBox = document.getElementById("trabajador_suggest");

  const bloqueContexto = document.getElementById("bloque_contexto_trabajador");
  const ctxNombre = document.getElementById("ctx_nombre");
  const ctxRut = document.getElementById("ctx_rut");
  const ctxObra = document.getElementById("ctx_obra");
  const ctxEmpleador = document.getElementById("ctx_empleador");

  const bloqueContratos = document.getElementById("bloque_contratos");
  const contratosOpciones = document.getElementById("contratos_opciones");

  const bloqueContextoContrato = document.getElementById("bloque_contexto_contrato");
  const ctx2Contrato = document.getElementById("ctx2_contrato");
  const ctx2Tipo = document.getElementById("ctx2_tipo");
  const ctx2Empleador = document.getElementById("ctx2_empleador");
  const ctx2Obra = document.getElementById("ctx2_obra");
  const ctx2Inicio = document.getElementById("ctx2_inicio");
  const ctx2Termino = document.getElementById("ctx2_termino");

  const fechaInicio = document.getElementById("fecha_inicio");
  const fechaTermino = document.getElementById("fecha_termino");
  const alertaFechas = document.getElementById("alerta_fechas_pacto");
  const btnGuardar = document.getElementById("btn_guardar_pacto");

  if (!form || !fechaInicio || !fechaTermino || !alertaFechas || !btnGuardar) return;

  const searchUrl = form.dataset.apiTrabajadoresBuscar || "";
  const contratosUrl = form.dataset.apiTrabajadorContratos || "";
  const modo = form.dataset.modo || (inputBuscar ? "nuevo" : "editar");

  let debounceTimer = null;
  let terminoAutoCalculado = true;

  function parseDateLocal(value) {
    if (!value) return null;
    const parts = value.split("-");
    if (parts.length !== 3) return null;
    const y = parseInt(parts[0], 10);
    const m = parseInt(parts[1], 10);
    const d = parseInt(parts[2], 10);
    if (!y || !m || !d) return null;
    return new Date(y, m - 1, d);
  }

  function formatDateLocal(dateObj) {
    const y = dateObj.getFullYear();
    const m = String(dateObj.getMonth() + 1).padStart(2, "0");
    const d = String(dateObj.getDate()).padStart(2, "0");
    return `${y}-${m}-${d}`;
  }

  function lastDayOfMonth(year, monthIndexZeroBased) {
    return new Date(year, monthIndexZeroBased + 1, 0).getDate();
  }

  function calcularFechaTerminoPacto(fechaInicioStr) {
    const dt = parseDateLocal(fechaInicioStr);
    if (!dt) return "";

    const dia = dt.getDate();
    const mes = dt.getMonth();
    const anio = dt.getFullYear();

    if (dia === 1) {
      const mesObjetivo = mes + 2;
      const anioObjetivo = anio + Math.floor(mesObjetivo / 12);
      const mesNorm = mesObjetivo % 12;
      const ultimoDia = lastDayOfMonth(anioObjetivo, mesNorm);
      return formatDateLocal(new Date(anioObjetivo, mesNorm, ultimoDia));
    }

    const mesObjetivo = mes + 3;
    const anioObjetivo = anio + Math.floor(mesObjetivo / 12);
    const mesNorm = mesObjetivo % 12;
    const ultimoDia = lastDayOfMonth(anioObjetivo, mesNorm);
    const diaFinal = Math.min(dia, ultimoDia);

    return formatDateLocal(new Date(anioObjetivo, mesNorm, diaFinal));
  }

  function rangoValidoPacto(fechaInicioStr, fechaTerminoStr) {
    const ini = parseDateLocal(fechaInicioStr);
    const fin = parseDateLocal(fechaTerminoStr);

    if (!ini || !fin) return false;
    if (fin < ini) return false;

    const fechaMax = calcularFechaTerminoPacto(fechaInicioStr);
    if (!fechaMax) return false;

    return fechaTerminoStr <= fechaMax;
  }

  function refrescarValidacionFechas() {
    const ini = fechaInicio.value;
    const fin = fechaTermino.value;

    if (!ini || !fin) {
      alertaFechas.classList.add("d-none");
      btnGuardar.disabled = false;
      return;
    }

    const valido = rangoValidoPacto(ini, fin);
    alertaFechas.classList.toggle("d-none", valido);
    btnGuardar.disabled = !valido;
  }

  function autocalcularFechaTermino() {
    if (!terminoAutoCalculado && fechaTermino.value) return;

    const nuevaFecha = calcularFechaTerminoPacto(fechaInicio.value);
    if (nuevaFecha) fechaTermino.value = nuevaFecha;
    refrescarValidacionFechas();
  }

  function clearSuggest() {
    if (!suggestBox) return;
    suggestBox.innerHTML = "";
    suggestBox.style.display = "none";
  }

  function clearContexto() {
    if (bloqueContexto) bloqueContexto.style.display = "none";
    if (ctxNombre) ctxNombre.textContent = "-";
    if (ctxRut) ctxRut.textContent = "-";
    if (ctxObra) ctxObra.textContent = "-";
    if (ctxEmpleador) ctxEmpleador.textContent = "-";
  }

  function setContexto(t) {
    if (!t) {
      clearContexto();
      return;
    }

    if (ctxNombre) ctxNombre.textContent = t.nombre || "-";
    if (ctxRut) ctxRut.textContent = t.rut || "-";
    if (ctxObra) ctxObra.textContent = t.obra || "-";
    if (ctxEmpleador) ctxEmpleador.textContent = t.empleador || "-";
    if (bloqueContexto) bloqueContexto.style.display = "";
  }

  function clearContextoContrato() {
    if (bloqueContextoContrato) bloqueContextoContrato.style.display = "none";
    if (ctx2Contrato) ctx2Contrato.textContent = "-";
    if (ctx2Tipo) ctx2Tipo.textContent = "-";
    if (ctx2Empleador) ctx2Empleador.textContent = "-";
    if (ctx2Obra) ctx2Obra.textContent = "-";
    if (ctx2Inicio) ctx2Inicio.textContent = "-";
    if (ctx2Termino) ctx2Termino.textContent = "-";
  }

  function clearContratos() {
    if (inputContratoId) inputContratoId.value = "";
    if (contratosOpciones) contratosOpciones.innerHTML = "";
    if (bloqueContratos) bloqueContratos.style.display = "none";
    clearContextoContrato();
  }

  function setContextoContrato(c) {
    if (!c) {
      clearContextoContrato();
      return;
    }

    if (ctx2Contrato) ctx2Contrato.textContent = "#" + (c.id || "-");
    if (ctx2Tipo) ctx2Tipo.textContent = c.tipo_contrato || "-";
    if (ctx2Empleador) ctx2Empleador.textContent = c.empleador || "-";
    if (ctx2Obra) ctx2Obra.textContent = c.obra || "-";
    if (ctx2Inicio) ctx2Inicio.textContent = c.fecha_inicio || "-";
    if (ctx2Termino) ctx2Termino.textContent = c.fecha_termino || "Sin término";
    if (bloqueContextoContrato) bloqueContextoContrato.style.display = "";
  }

  function renderContratos(items) {
    if (!contratosOpciones) return;

    contratosOpciones.innerHTML = "";

    if (!items || items.length === 0) {
      const div = document.createElement("div");
      div.className = "text-muted";
      div.textContent = "No se encontraron contratos para este trabajador.";
      contratosOpciones.appendChild(div);
      if (bloqueContratos) bloqueContratos.style.display = "";
      return;
    }

    items.forEach((c, idx) => {
      const wrapper = document.createElement("label");
      wrapper.className = "border rounded-3 p-3 bg-white";
      wrapper.style.cursor = "pointer";

      const check = document.createElement("div");
      check.className = "form-check m-0";

      const radio = document.createElement("input");
      radio.className = "form-check-input me-2";
      radio.type = "radio";
      radio.name = "contrato_selector_ui";
      radio.value = c.id || "";
      radio.checked = idx === 0;

      const label = document.createElement("span");
      label.className = "fw-semibold";
      label.textContent = c.label || "Contrato";

      check.appendChild(radio);
      check.appendChild(label);

      const meta = document.createElement("div");
      meta.className = "small text-muted mt-1 ms-4";
      meta.textContent = `Estado: ${c.estado_contrato || "-"} · Inicio: ${c.fecha_inicio || "-"} · Término: ${c.fecha_termino || "Sin término"}`;

      wrapper.appendChild(check);
      wrapper.appendChild(meta);

      radio.addEventListener("change", function () {
        if (this.checked) {
          if (inputContratoId) inputContratoId.value = c.id || "";
          setContextoContrato(c);
        }
      });

      contratosOpciones.appendChild(wrapper);
    });

    if (bloqueContratos) bloqueContratos.style.display = "";

    if (items[0]) {
      if (inputContratoId) inputContratoId.value = items[0].id || "";
      setContextoContrato(items[0]);
    }
  }

  function showSuggest(items) {
    if (!suggestBox) return;

    suggestBox.innerHTML = "";

    if (!items || items.length === 0) {
      suggestBox.style.display = "none";
      return;
    }

    items.forEach((t) => {
      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = "list-group-item list-group-item-action";

      const row = document.createElement("div");
      row.className = "d-flex justify-content-between align-items-start gap-3";

      const left = document.createElement("div");
      const name = document.createElement("div");
      const strong = document.createElement("strong");
      strong.textContent = t.nombre || "";
      name.appendChild(strong);

      const meta = document.createElement("div");
      meta.className = "small text-muted";
      meta.textContent = t.obra ? `Obra: ${t.obra}` : "Sin obra informada";

      left.appendChild(name);
      left.appendChild(meta);

      const rut = document.createElement("div");
      rut.className = "text-muted small text-nowrap";
      rut.textContent = t.rut || "";

      row.appendChild(left);
      row.appendChild(rut);
      btn.appendChild(row);

      btn.addEventListener("click", async function () {
        inputId.value = t.id || "";
        inputBuscar.value = `${t.nombre || ""} · ${t.rut || ""}`;
        setContexto(t);
        clearSuggest();
        await cargarContratosTrabajador(t.id);
      });

      suggestBox.appendChild(btn);
    });

    suggestBox.style.display = "";
  }

  async function buscarTrabajadores(q) {
    if (!searchUrl) return;
    const url = new URL(searchUrl, window.location.origin);
    url.searchParams.set("q", q);

    const res = await fetch(url.toString(), { headers: { Accept: "application/json" } });

    if (!res.ok) {
      clearSuggest();
      return;
    }

    const data = await res.json();
    showSuggest(data.results || []);
  }

  async function cargarContratosTrabajador(trabajadorId) {
    clearContratos();
    if (!trabajadorId || !contratosUrl) return;

    const url = new URL(contratosUrl, window.location.origin);
    url.searchParams.set("trabajador_id", trabajadorId);

    const res = await fetch(url.toString(), { headers: { Accept: "application/json" } });
    if (!res.ok) return;

    const data = await res.json();
    renderContratos(data.results || []);
  }

  if (inputBuscar && inputId && suggestBox) {
    inputBuscar.addEventListener("input", function () {
      const q = inputBuscar.value.trim();

      inputId.value = "";
      if (inputContratoId) inputContratoId.value = "";
      clearContexto();
      clearContratos();

      if (debounceTimer) clearTimeout(debounceTimer);

      if (q.length < 2) {
        clearSuggest();
        return;
      }

      debounceTimer = setTimeout(() => buscarTrabajadores(q), 250);
    });

    inputBuscar.addEventListener("focus", function () {
      const q = inputBuscar.value.trim();
      if (q.length >= 2 && !inputId.value) buscarTrabajadores(q);
    });

    document.addEventListener("click", function (ev) {
      if (!suggestBox.contains(ev.target) && ev.target !== inputBuscar) clearSuggest();
    });
  }

  fechaInicio.addEventListener("change", function () {
    if (modo === "nuevo") {
      terminoAutoCalculado = true;
      autocalcularFechaTermino();
    } else {
      refrescarValidacionFechas();
    }
  });

  fechaTermino.addEventListener("input", function () {
    terminoAutoCalculado = false;
    refrescarValidacionFechas();
  });

  fechaTermino.addEventListener("change", function () {
    terminoAutoCalculado = false;
    refrescarValidacionFechas();
  });

  form.addEventListener("submit", function (ev) {
    if (modo === "nuevo") {
      if (inputId && !inputId.value) {
        ev.preventDefault();
        alert("Debes seleccionar un trabajador desde la lista de resultados.");
        if (inputBuscar) inputBuscar.focus();
        return;
      }

      if (inputContratoId && !inputContratoId.value) {
        ev.preventDefault();
        alert("Debes seleccionar el contrato que se utilizará para emitir el pacto.");
        return;
      }
    }

    refrescarValidacionFechas();
    if (btnGuardar.disabled) {
      ev.preventDefault();
      alert("Las fechas del pacto exceden la vigencia máxima permitida de 3 meses.");
    }
  });

  if (modo === "nuevo") autocalcularFechaTermino();
  refrescarValidacionFechas();
})();
