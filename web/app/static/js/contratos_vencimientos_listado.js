// Funciones de apoyo para el módulo de vencimientos de contratos.
(function () {
  // -----------------------------
  // Helpers UI / fetch
  // -----------------------------
  function escapeHtml(s) {
    return (s || "").replace(/[&<>"']/g, (c) => ({
      "&": "&amp;", "<": "&lt;", ">": "&lt;", '"': "&quot;", "'": "&#039;"
    }[c]));
  }

  async function fetchJSON(url) {
    const res = await fetch(url, { headers: { "X-Requested-With": "XMLHttpRequest" } });

    const ct = (res.headers.get("content-type") || "").toLowerCase();
    if (!res.ok) {
      const txt = await res.text().catch(() => "");
      throw new Error("HTTP " + res.status + " " + (txt ? (":: " + txt.slice(0, 120)) : ""));
    }

    if (ct.includes("application/json")) {
      return await res.json();
    }

    const txt = await res.text().catch(() => "");
    throw new Error("Respuesta no JSON: " + (txt ? txt.slice(0, 120) : "(vacía)"));
  }

  function ensureRelativeWrapper(inputEl) {
    const p = inputEl.parentElement;
    if (p && p.classList.contains("js-ac-wrapper")) return p;

    const wrapper = document.createElement("div");
    wrapper.className = "position-relative js-ac-wrapper";
    inputEl.parentNode.insertBefore(wrapper, inputEl);
    wrapper.appendChild(inputEl);
    return wrapper;
  }

  function buildDropdownForInput(inputEl) {
    const wrapper = ensureRelativeWrapper(inputEl);

    let box = wrapper.querySelector(".js-ac-dropdown");
    if (box) return box;

    box = document.createElement("div");
    box.className = "list-group position-absolute shadow-sm js-ac-dropdown";
    box.style.zIndex = "1080";
    box.style.maxHeight = "260px";
    box.style.overflow = "auto";
    box.style.width = "100%";
    box.style.top = "calc(100% + 2px)";
    box.style.left = "0";
    box.style.display = "none";

    wrapper.appendChild(box);
    return box;
  }

  function closeDropdown(dropdown) {
    if (!dropdown) return;
    dropdown.style.display = "none";
    dropdown.innerHTML = "";
  }

  function openDropdown(dropdown) {
    if (!dropdown) return;
    dropdown.style.display = "";
  }

  function clearSelect(selectEl, placeholder) {
    selectEl.innerHTML = "";
    const opt = document.createElement("option");
    opt.value = "";
    opt.textContent = placeholder || "—";
    selectEl.appendChild(opt);
  }

  async function loadContratosForTrabajador(trabajadorId, selectEl) {
    selectEl.disabled = true;
    clearSelect(selectEl, "Cargando contratos…");

    const baseUrl = document.getElementById("contratos-vencimientos-config")?.dataset.apiContratosUrl || "";
    const url = baseUrl + "?trabajador_id=" + encodeURIComponent(trabajadorId);

    const data = await fetchJSON(url);
    const items = (data && data.results) ? data.results : [];

    clearSelect(selectEl, items.length ? "Selecciona un contrato…" : "Sin contratos disponibles");

    for (const c of items) {
      const opt = document.createElement("option");
      opt.value = c.id;
      opt.textContent = c.label || ("Contrato #" + c.id);
      selectEl.appendChild(opt);
    }

    selectEl.disabled = (items.length === 0);

    if (items.length === 1) {
      selectEl.value = String(items[0].id);
    }
  }

  // -----------------------------
  // Helpers fechas sugeridas (EXTENDER / TERMINAR)
  // -----------------------------
  function parseIsoDate(iso) {
    if (!iso || typeof iso !== "string") return null;
    const m = iso.match(/^(\d{4})-(\d{2})-(\d{2})$/);
    if (!m) return null;
    const y = Number(m[1]);
    const mo = Number(m[2]); // 1-12
    const d = Number(m[3]);
    if (!y || !mo || !d) return null;
    return { y, mo, d };
  }

  function pad2(n) { return String(n).padStart(2, "0"); }

  function toIsoDate(y, mo, d) {
    return `${y}-${pad2(mo)}-${pad2(d)}`;
  }

  function lastDayOfMonth(y, mo) {
    // mo: 1-12, JS Date monthIndex 0-11, day=0 => último día del mes anterior
    return new Date(y, mo, 0).getDate();
  }

  function addMonthsEOM(terminoIso, monthsToAdd) {
    // Sugerencia: siempre último día del mes resultante (ideal para contratos fin de mes)
    const p = parseIsoDate(terminoIso);
    if (!p) return "";

    let y = p.y;
    let mo = p.mo + (monthsToAdd || 0);

    while (mo > 12) { mo -= 12; y += 1; }
    while (mo < 1)  { mo += 12; y -= 1; }

    const d = lastDayOfMonth(y, mo);
    return toIsoDate(y, mo, d);
  }

  // -----------------------------
  // Estado filas
  // -----------------------------
  function applyRowState(row) {
    const accionSel = row.querySelector(".js-accion");
    const nuevaFecha = row.querySelector(".js-nueva-fecha");
    const fechaConf = row.querySelector(".js-fecha-conf");

    const hintExt = row.querySelector(".js-hint-ext");
    const hintTer = row.querySelector(".js-hint-ter");

    const terminoIso = row.getAttribute("data-termino-iso") || "";
    const puedeExtender = (row.getAttribute("data-puede-extender") || "1") === "1";

    let accion = (accionSel.value || "PENDIENTE").toUpperCase();

    // Si por alguna razón quedó EXTENDER seleccionado pero no corresponde, lo corregimos.
    if (accion === "EXTENDER" && !puedeExtender) {
      accionSel.value = "PENDIENTE";
      accion = "PENDIENTE";
    }

    // Reset base
    nuevaFecha.disabled = true;
    fechaConf.disabled = true;
    if (hintExt) hintExt.style.display = "none";
    if (hintTer) hintTer.style.display = "none";

    if (accion === "EXTENDER") {
      nuevaFecha.disabled = false;
      if (hintExt) hintExt.style.display = "";
      fechaConf.value = "";

      // ✅ Sugerencia Ext.: 3 meses posterior al término actual, al último día del mes
      if (!nuevaFecha.value && terminoIso) {
        nuevaFecha.value = addMonthsEOM(terminoIso, 3);
      }

    } else if (accion === "TERMINAR") {
      fechaConf.disabled = false;
      if (hintTer) hintTer.style.display = "";

      // ✅ Sugerencia Term.: fecha de término del contrato
      if (!fechaConf.value && terminoIso) {
        fechaConf.value = terminoIso;
      }

      nuevaFecha.value = "";
    } else if (accion === "INDEFINIDO") {
      nuevaFecha.value = "";
      fechaConf.value = "";
    } else {
      nuevaFecha.value = "";
      fechaConf.value = "";
    }

    // Si no puede extender, el input de nueva fecha debe quedar bloqueado siempre
    if (!puedeExtender) {
      nuevaFecha.disabled = true;
      nuevaFecha.value = "";
      if (hintExt) hintExt.style.display = "none";
    }
  }

  function applyExtraState(form) {
    const accionSel = form.querySelector(".js-accion-extra");
    const nuevaFecha = form.querySelector(".js-nueva-fecha-extra");
    const fechaConf = form.querySelector(".js-fecha-conf-extra");
    const hintExt = form.querySelector(".js-hint-ext-extra");
    const hintTer = form.querySelector(".js-hint-ter-extra");

    const accion = (accionSel.value || "TERMINAR").toUpperCase();

    nuevaFecha.disabled = true;
    fechaConf.disabled = true;
    if (hintExt) hintExt.style.display = "none";
    if (hintTer) hintTer.style.display = "none";

    if (accion === "EXTENDER") {
      nuevaFecha.disabled = false;
      if (hintExt) hintExt.style.display = "";
      fechaConf.value = "";
    } else if (accion === "TERMINAR") {
      fechaConf.disabled = false;
      if (hintTer) hintTer.style.display = "";
      nuevaFecha.value = "";
    } else if (accion === "INDEFINIDO") {
      nuevaFecha.value = "";
      fechaConf.value = "";
    } else {
      nuevaFecha.value = "";
      fechaConf.value = "";
    }
  }

  // -----------------------------
  // Autocomplete trabajador (extra)
  // -----------------------------
  function setupTrabajadorAutocompleteExtra(extraForm) {
    const input = extraForm.querySelector(".js-trabajador-q-extra");
    const hidId = extraForm.querySelector(".js-trabajador-id-extra");
    const contratoSel = extraForm.querySelector(".js-contrato-select-extra");

    if (!input || !hidId || !contratoSel) return;

    const dropdown = buildDropdownForInput(input);

    let debounce = null;
    let lastQuery = "";

    function resetSelection() {
      hidId.value = "";
      contratoSel.disabled = true;
      clearSelect(contratoSel, "Primero selecciona un trabajador…");
    }

    input.addEventListener("input", function () {
      const q = (input.value || "").trim();

      resetSelection();
      closeDropdown(dropdown);

      if (q.length < 2) return;

      lastQuery = q;

      if (debounce) clearTimeout(debounce);
      debounce = setTimeout(async () => {
        try {
          const baseUrl = document.getElementById("contratos-vencimientos-config")?.dataset.apiTrabajadoresUrl || "";
          const url = baseUrl + "?q=" + encodeURIComponent(q);
          const data = await fetchJSON(url);
          const items = (data && data.results) ? data.results : [];

          if (((input.value || "").trim()) !== lastQuery) return;

          dropdown.innerHTML = "";

          if (!items.length) {
            const empty = document.createElement("div");
            empty.className = "list-group-item small text-muted";
            empty.textContent = "Sin resultados…";
            dropdown.appendChild(empty);
            openDropdown(dropdown);
            return;
          }

          for (const t of items) {
            const btn = document.createElement("button");
            btn.type = "button";
            btn.className = "list-group-item list-group-item-action";

            const estado = (t.estado || "").toUpperCase();
            const badge = (estado && estado !== "VIGENTE")
              ? `<span class="badge text-bg-secondary ms-2">NO VIGENTE</span>`
              : "";

            btn.innerHTML = `
              <div class="fw-semibold d-flex align-items-center">
                <span>${escapeHtml(t.nombre || "")}</span>
                ${badge}
              </div>
              <div class="small text-muted">${escapeHtml(t.rut || "")}</div>
            `;

            btn.addEventListener("mousedown", function (ev) {
              ev.preventDefault();
            });

            btn.addEventListener("click", async () => {
              input.value = (t.nombre || "").trim();
              hidId.value = t.id;

              closeDropdown(dropdown);

              try {
                await loadContratosForTrabajador(t.id, contratoSel);
              } catch (e) {
                console.error("Carga contratos trabajador:", e);
                contratoSel.disabled = true;
                clearSelect(contratoSel, "No se pudieron cargar contratos");
              }
            });

            dropdown.appendChild(btn);
          }

          openDropdown(dropdown);
        } catch (e) {
          console.error("Autocomplete trabajadores:", e);

          dropdown.innerHTML = "";
          const err = document.createElement("div");
          err.className = "list-group-item small text-danger";
          err.textContent = "Error consultando trabajadores: " + (e && e.message ? e.message : "desconocido");
          dropdown.appendChild(err);
          openDropdown(dropdown);
        }
      }, 220);
    });

    input.addEventListener("blur", function () {
      setTimeout(() => closeDropdown(dropdown), 180);
    });

    input.addEventListener("keydown", function (ev) {
      if (ev.key === "Escape") {
        closeDropdown(dropdown);
      }
    });
  }

  // -----------------------------
  // DOM Ready
  // -----------------------------
  document.addEventListener("DOMContentLoaded", function () {
    document.querySelectorAll(".js-row").forEach((row) => {
      const sel = row.querySelector(".js-accion");
      if (!sel) return;

      applyRowState(row);
      sel.addEventListener("change", function () {
        applyRowState(row);
      });
    });

    const extraForm = document.querySelector(".js-extra-form");
    if (extraForm) {
      const sel = extraForm.querySelector(".js-accion-extra");
      applyExtraState(extraForm);

      if (sel) {
        sel.addEventListener("change", function () {
          applyExtraState(extraForm);
        });
      }

      setupTrabajadorAutocompleteExtra(extraForm);
    }
  });
})();
