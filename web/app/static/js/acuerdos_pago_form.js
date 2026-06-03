function el(id){ return document.getElementById(id); }

  // ============================
  // Suggest UI helpers
  // ============================
  function clearSuggest(){
    const box = el("trabajador_suggest");
    if (box) { box.innerHTML = ""; box.style.display = "none"; }
  }

  function showSuggest(items){
    const box = el("trabajador_suggest");
    if (!box) return;

    box.innerHTML = "";
    if (!items || items.length === 0) {
      box.style.display = "none";
      return;
    }

    items.forEach((t) => {
      const a = document.createElement("button");
      a.type = "button";
      a.className = "list-group-item list-group-item-action";
      a.innerHTML = `<div class="d-flex justify-content-between gap-2">
          <div><strong>${(t.nombre || "").toUpperCase()}</strong></div>
          <div class="text-muted">${t.rut || ""}</div>
        </div>`;
      a.addEventListener("click", () => selectTrabajador(t));
      box.appendChild(a);
    });

    box.style.display = "";
  }

  // ============================
  // Contexto (empleadores/obras)
  // ============================
  let CACHE_CTX = null;

  async function loadContexto(trabajadorId = null){
    const form = el("form-acuerdo-pago");
    const url = new URL(form?.dataset.apiContextoUrl || "", window.location.origin);
    if (trabajadorId) url.searchParams.set("trabajador_id", trabajadorId);

    const res = await fetch(url.toString(), { headers: { "Accept": "application/json" } });
    const data = await res.json();
    CACHE_CTX = data;

    fillSelectsContext(data);
    return data;
  }

  function fillSelect(selectEl, options, selectedId){
    if (!selectEl) return;

    const first = selectEl.querySelector("option");
    selectEl.innerHTML = "";
    if (first) selectEl.appendChild(first);

    (options || []).forEach((o) => {
      const opt = document.createElement("option");
      opt.value = o.id;
      opt.textContent = o.label;
      if (String(selectedId || "") === String(o.id)) opt.selected = true;
      selectEl.appendChild(opt);
    });
  }

  function fillSelectsContext(data){
    const form = el("form-acuerdo-pago");
    const cur_empleador = form?.dataset.empleadorActualId || "";
    const cur_obra = form?.dataset.obraActualId || "";

    fillSelect(el("empleador_id"), (data && data.empleadores) ? data.empleadores : [], cur_empleador);
    fillSelect(el("obra_id"), (data && data.obras) ? data.obras : [], cur_obra);
  }

  function setContextSuggest(suggest){
    if (!suggest) return;

    const emp = el("empleador_id");
    const obra = el("obra_id");

    if (emp && suggest.empleador_id) emp.value = String(suggest.empleador_id);
    if (obra && suggest.obra_id) obra.value = String(suggest.obra_id);
  }

  // ============================
  // Autocomplete trabajadores
  // ============================
  let tTimer = null;

  async function searchTrabajadores(q){
    const form = el("form-acuerdo-pago");
    const url = new URL(form?.dataset.apiTrabajadoresUrl || "", window.location.origin);
    url.searchParams.set("q", q);

    const res = await fetch(url.toString(), { headers: { "Accept": "application/json" } });
    const data = await res.json();
    return (data && data.results) ? data.results : [];
  }

  async function onTrabInput(){
    const inp = el("trabajador_buscar");
    if (!inp) return;

    const q = (inp.value || "").trim();
    if (q.length < 2) { clearSuggest(); return; }

    const results = await searchTrabajadores(q);
    showSuggest(results);
  }

  async function selectTrabajador(t){
    el("trabajador_id").value = t.id;
    el("trabajador_buscar").value = `${t.nombre || ""} (${t.rut || ""})`;
    clearSuggest();

    const ctx = await loadContexto(t.id);
    if (ctx && ctx.suggest) setContextSuggest(ctx.suggest);

    // al cambiar trabajador, recalculamos cuota (por si venía algo raro)
    recalcCuota();
  }

  // ============================
  // Cálculo cuota (CLP sin decimales)
  // ============================
  function parseCLPInt(s){
    const onlyDigits = String(s || "").replace(/[^0-9]/g, "");
    if (!onlyDigits) return 0;
    return parseInt(onlyDigits, 10) || 0;
  }

  function recalcCuota(){
    const totalEl = el("monto_total");
    const cuotasEl = el("cuotas");
    const cuotaEl = el("monto_cuota");
    if (!totalEl || !cuotasEl || !cuotaEl) return;

    const total = parseCLPInt(totalEl.value);
    const cuotas = Math.max(1, parseInt(cuotasEl.value || "1", 10) || 1);

    cuotaEl.value = String(Math.floor(total / cuotas));
  }

  // ============================
  // Init (UNA sola vez)
  // ============================
  document.addEventListener("DOMContentLoaded", async function() {
    // carga selects y mantiene selección en editar
    await loadContexto();

    const inp = el("trabajador_buscar");
    if (inp) {
      inp.addEventListener("input", function(){
        if (tTimer) clearTimeout(tTimer);
        tTimer = setTimeout(onTrabInput, 220);
      });

      inp.addEventListener("blur", function(){
        setTimeout(clearSuggest, 200);
      });

      inp.addEventListener("focus", function(){
        const q = (inp.value || "").trim();
        if (q.length >= 2) onTrabInput();
      });
    }

    // si venimos editando con trabajador_id, sugerimos empleador/obra
    const existingId = (el("trabajador_id").value || "").trim();
    if (existingId) {
      const ctx = await loadContexto(existingId);
      if (ctx && ctx.suggest) setContextSuggest(ctx.suggest);
    }

    // listeners cuota
    const totalEl = el("monto_total");
    const cuotasEl = el("cuotas");
    if (totalEl) totalEl.addEventListener("input", recalcCuota);
    if (cuotasEl) cuotasEl.addEventListener("input", recalcCuota);

    // inicial
    recalcCuota();
  });
