(function () {
  const form = document.getElementById("egreso-form");

  function el(id) {
    return document.getElementById(id);
  }

  function setDisabledWithin(container, disabled) {
    if (!container) return;
    const fields = container.querySelectorAll("input, select, textarea, button");
    fields.forEach((node) => {
      if (!node || node.id === "modo_beneficiario") return;
      node.disabled = Boolean(disabled);
    });
  }

  function syncPills(modo) {
    const pillTrab = el("pill_trab");
    const pillExt = el("pill_ext");

    if (pillTrab) {
      pillTrab.classList.toggle("active", modo === "TRABAJADOR");
      pillTrab.setAttribute("aria-selected", modo === "TRABAJADOR" ? "true" : "false");
    }

    if (pillExt) {
      pillExt.classList.toggle("active", modo === "EXTERNO");
      pillExt.setAttribute("aria-selected", modo === "EXTERNO" ? "true" : "false");
    }
  }

  function toggleBeneficiario() {
    const select = el("modo_beneficiario");
    const modo = select ? select.value || "TRABAJADOR" : "TRABAJADOR";
    const bloqueTrabajador = el("bloque_trabajador");
    const bloqueExterno = el("bloque_externo");

    if (modo === "EXTERNO") {
      if (bloqueTrabajador) bloqueTrabajador.style.display = "none";
      if (bloqueExterno) bloqueExterno.style.display = "";
      setDisabledWithin(bloqueTrabajador, true);
      setDisabledWithin(bloqueExterno, false);
      return;
    }

    if (bloqueTrabajador) bloqueTrabajador.style.display = "";
    if (bloqueExterno) bloqueExterno.style.display = "none";
    setDisabledWithin(bloqueTrabajador, false);
    setDisabledWithin(bloqueExterno, true);
  }

  function setModoBeneficiario(modo) {
    const select = el("modo_beneficiario");
    if (select) select.value = modo;
    syncPills(modo);
    toggleBeneficiario();
  }

  function clearSuggest() {
    const box = el("trabajador_suggest");
    if (!box) return;
    box.innerHTML = "";
    box.style.display = "none";
  }

  function showSuggest(items) {
    const box = el("trabajador_suggest");
    if (!box) return;

    box.innerHTML = "";
    if (!items || items.length === 0) {
      box.style.display = "none";
      return;
    }

    items.forEach((trabajador) => {
      const button = document.createElement("button");
      button.type = "button";
      button.className = "list-group-item list-group-item-action";
      button.innerHTML = `<div class="d-flex justify-content-between gap-2">
          <div><strong>${(trabajador.nombre || "").toUpperCase()}</strong></div>
          <div class="text-muted">${trabajador.rut || ""}</div>
        </div>`;
      button.addEventListener("click", () => selectTrabajador(trabajador));
      box.appendChild(button);
    });

    box.style.display = "";
  }

  function fillSelect(selectEl, options, selectedId) {
    if (!selectEl) return;

    const first = selectEl.querySelector("option");
    selectEl.innerHTML = "";
    if (first) selectEl.appendChild(first);

    (options || []).forEach((optionData) => {
      const option = document.createElement("option");
      option.value = optionData.id;
      option.textContent = optionData.label;
      if (String(selectedId || "") === String(optionData.id)) option.selected = true;
      selectEl.appendChild(option);
    });
  }

  function fillSelectsContext(data) {
    const empleadorId = form?.dataset.egresoEmpleadorId || "";
    const obraId = form?.dataset.egresoObraId || "";

    fillSelect(el("empleador_id_trab"), data.empleadores, empleadorId);
    fillSelect(el("obra_id_trab"), data.obras, obraId);
    fillSelect(el("empleador_id_ext"), data.empleadores, empleadorId);
    fillSelect(el("obra_id_ext"), data.obras, obraId);
  }

  function setContextSuggest(suggest) {
    if (!suggest) return;

    const empleadorTrab = el("empleador_id_trab");
    const obraTrab = el("obra_id_trab");

    if (empleadorTrab && suggest.empleador_id) empleadorTrab.value = String(suggest.empleador_id);
    if (obraTrab && suggest.obra_id) obraTrab.value = String(suggest.obra_id);
  }

  async function loadContexto(trabajadorId = null) {
    const contextoUrl = form?.dataset.contextoUrl;
    if (!contextoUrl) return null;

    const url = new URL(contextoUrl, window.location.origin);
    if (trabajadorId) url.searchParams.set("trabajador_id", trabajadorId);

    const response = await fetch(url.toString(), { headers: { Accept: "application/json" } });
    const data = await response.json();
    fillSelectsContext(data);
    return data;
  }

  async function searchTrabajadores(q) {
    const trabajadoresUrl = form?.dataset.trabajadoresUrl;
    if (!trabajadoresUrl) return [];

    const url = new URL(trabajadoresUrl, window.location.origin);
    url.searchParams.set("q", q);

    const response = await fetch(url.toString(), { headers: { Accept: "application/json" } });
    const data = await response.json();
    return data && data.results ? data.results : [];
  }

  async function onTrabajadorInput() {
    const input = el("trabajador_buscar");
    if (!input) return;

    const q = (input.value || "").trim();
    if (q.length < 2) {
      clearSuggest();
      return;
    }

    const results = await searchTrabajadores(q);
    showSuggest(results);
  }

  async function selectTrabajador(trabajador) {
    const trabajadorId = el("trabajador_id");
    const trabajadorBuscar = el("trabajador_buscar");

    if (trabajadorId) trabajadorId.value = trabajador.id;
    if (trabajadorBuscar) trabajadorBuscar.value = `${trabajador.nombre || ""} (${trabajador.rut || ""})`;
    clearSuggest();

    const ctx = await loadContexto(trabajador.id);
    if (ctx && ctx.suggest) setContextSuggest(ctx.suggest);
  }

  document.addEventListener("DOMContentLoaded", async function () {
    const pillTrab = el("pill_trab");
    const pillExt = el("pill_ext");
    const select = el("modo_beneficiario");
    const input = el("trabajador_buscar");
    let timer = null;

    if (pillTrab) pillTrab.addEventListener("click", () => setModoBeneficiario("TRABAJADOR"));
    if (pillExt) pillExt.addEventListener("click", () => setModoBeneficiario("EXTERNO"));

    const modoInit = select ? select.value || "TRABAJADOR" : "TRABAJADOR";
    syncPills(modoInit);
    toggleBeneficiario();

    await loadContexto();

    if (input) {
      input.addEventListener("input", function () {
        if (timer) clearTimeout(timer);
        timer = setTimeout(onTrabajadorInput, 220);
      });

      input.addEventListener("blur", function () {
        setTimeout(clearSuggest, 200);
      });

      input.addEventListener("focus", function () {
        const q = (input.value || "").trim();
        if (q.length >= 2) onTrabajadorInput();
      });
    }

    const existingId = (el("trabajador_id")?.value || "").trim();
    if (existingId) {
      const ctx = await loadContexto(existingId);
      if (ctx && ctx.suggest) setContextSuggest(ctx.suggest);
    }
  });
})();
