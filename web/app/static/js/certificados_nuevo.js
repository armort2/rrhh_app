(function () {
  const search = document.getElementById("workerSearch");
  const suggest = document.getElementById("workerSuggest");
  const btnSelect = document.getElementById("btnSelectWorker");
  const hiddenId = document.getElementById("trabajador_id");
  const selectedLabel = document.getElementById("selectedWorkerLabel");
  const step2 = document.getElementById("step2Card");

  const objetivoPreset = document.getElementById("objetivo_preset");
  const objetivoCustom = document.getElementById("objetivo_custom");
  const objetivoFinal = document.getElementById("objetivo_final");

  // Si algo crítico no existe, salimos sin romper la página
  if (!search || !suggest || !btnSelect || !hiddenId || !selectedLabel || !step2) {
    console.error("Certificados/nuevo: faltan elementos esperados en el DOM.");
    return;
  }

  let selected = null;
  let timer = null;

  function computeObjetivo() {
    const custom = (objetivoCustom?.value || "").trim();
    const preset = (objetivoPreset?.value || "").trim();
    objetivoFinal.value = custom || preset || "";
  }

  function hideSuggest() {
    suggest.classList.add("d-none");
  }

  function showSuggest(items) {
    suggest.innerHTML = "";
    if (!items || !items.length) {
      hideSuggest();
      return;
    }
    for (const it of items) {
      const b = document.createElement("button");
      b.type = "button";
      b.className = "list-group-item list-group-item-action";
      b.innerHTML = `<div class="fw-semibold">${it.label}</div>`;
      b.addEventListener("click", () => pickWorker(it));
      suggest.appendChild(b);
    }
    suggest.classList.remove("d-none");
  }

  function pickWorker(it) {
    selected = it;
    hiddenId.value = String(it.id);
    selectedLabel.textContent = it.label;
    search.value = it.label;
    btnSelect.disabled = false;
    hideSuggest();
  }

  async function fetchWorkers(q) {
    const endpoint = search.dataset.apiUrl || "";
    const url = endpoint + "?q=" + encodeURIComponent(q);
    const res = await fetch(url, { headers: { "Accept": "application/json" } });
    if (!res.ok) return [];
    return await res.json();
  }

  search.addEventListener("input", () => {
    selected = null;
    hiddenId.value = "";
    selectedLabel.textContent = "—";
    btnSelect.disabled = true;
    step2.classList.add("d-none");

    const q = (search.value || "").trim();
    if (timer) clearTimeout(timer);

    if (q.length < 2) {
      showSuggest([]);
      return;
    }

    timer = setTimeout(async () => {
      try {
        const items = await fetchWorkers(q);
        showSuggest(items);
      } catch (e) {
        console.error("Autocomplete error:", e);
        showSuggest([]);
      }
    }, 250);
  });

  document.addEventListener("click", (e) => {
    if (suggest.contains(e.target) || search.contains(e.target)) return;
    hideSuggest();
  });

  btnSelect.addEventListener("click", () => {
    if (!selected) return;
    step2.classList.remove("d-none");
    document.getElementById("tipo_cert")?.focus();
  });

  if (objetivoPreset) objetivoPreset.addEventListener("change", computeObjetivo);
  if (objetivoCustom) objetivoCustom.addEventListener("input", computeObjetivo);
  computeObjetivo();

  const form = document.getElementById("createCertForm");
  if (form) form.addEventListener("submit", computeObjetivo);
})();
