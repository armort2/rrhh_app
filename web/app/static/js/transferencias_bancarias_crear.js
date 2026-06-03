(() => {
  const searchInput = document.getElementById('benef-search');
  const suggBox = document.getElementById('benef-suggestions');
  const montoInput = document.getElementById('benef-monto');
  const glosaDefault = document.getElementById('glosa-default');

  const btnAdd = document.getElementById('btn-add');
  const rowsBody = document.getElementById('rows-body');

  const itemsJson = document.getElementById('items-json');
  const rowsCount = document.getElementById('rows-count');
  const rowsTotal = document.getElementById('rows-total');
  const frm = document.getElementById('frm-nomina');

  let picked = null;     // objeto seleccionado del autocomplete
  let timer = null;
  let rows = [];

  // estado UI sugerencias
  let lastSuggestions = [];
  let activeIdx = -1;

  function escapeHtml(s) {
    return String(s ?? '')
      .replaceAll('&', '&amp;')
      .replaceAll('<', '&lt;')
      .replaceAll('>', '&gt;')
      .replaceAll('"', '&quot;')
      .replaceAll("'", '&#39;');
  }

  function moneyCLP(n) {
    try {
      return (Number(n) || 0).toLocaleString('es-CL');
    } catch {
      return String(n);
    }
  }

  function setStats() {
    rowsCount.textContent = String(rows.length);
    const total = rows.reduce((a, r) => a + (Number(r.monto)||0), 0);
    rowsTotal.textContent = moneyCLP(total);
  }

  function hideSuggestions() {
    activeIdx = -1;
    lastSuggestions = [];
    suggBox.style.display = 'none';
    suggBox.innerHTML = '';
  }

  function highlightActive() {
    const items = suggBox.querySelectorAll('a.list-group-item');
    items.forEach((el, i) => {
      if (i === activeIdx) el.classList.add('active');
      else el.classList.remove('active');
    });
  }

  function pickSuggestion(item) {
    picked = item;
    searchInput.value = item.label || '';
    hideSuggestions();
    montoInput.focus();
  }

  function showSuggestions(list) {
    if (!list || list.length === 0) {
      hideSuggestions();
      return;
    }
    suggBox.innerHTML = '';
    lastSuggestions = list;
    activeIdx = -1;

    list.forEach((item, idx) => {
      const a = document.createElement('a');
      a.href = '#';
      a.className = 'list-group-item list-group-item-action';
      a.textContent = item.label;
      a.addEventListener('click', (ev) => {
        ev.preventDefault();
        pickSuggestion(item);
      });
      suggBox.appendChild(a);
    });

    suggBox.style.display = 'block';
  }

  async function fetchSuggestions(q) {
    const endpoint = frm?.dataset.apiBeneficiariosUrl || "";
    const url = endpoint + "?q=" + encodeURIComponent(q);
    const resp = await fetch(url, { headers: { 'Accept': 'application/json' }});
    if (!resp.ok) return [];
    const data = await resp.json();
    return data.results || [];
  }

  searchInput.addEventListener('input', () => {
    picked = null;
    const q = (searchInput.value || '').trim();

    if (timer) clearTimeout(timer);
    if (q.length < 2) {
      hideSuggestions();
      return;
    }

    timer = setTimeout(async () => {
      const list = await fetchSuggestions(q);
      showSuggestions(list);
    }, 180);
  });

  // teclado: Enter, Esc, flechas
  searchInput.addEventListener('keydown', (ev) => {
    if (suggBox.style.display !== 'block') return;

    if (ev.key === 'Escape') {
      ev.preventDefault();
      hideSuggestions();
      return;
    }

    if (ev.key === 'ArrowDown') {
      ev.preventDefault();
      activeIdx = Math.min(activeIdx + 1, lastSuggestions.length - 1);
      highlightActive();
      return;
    }

    if (ev.key === 'ArrowUp') {
      ev.preventDefault();
      activeIdx = Math.max(activeIdx - 1, 0);
      highlightActive();
      return;
    }

    if (ev.key === 'Enter') {
      // si hay uno activo, elegirlo; si no, elegir el primero
      ev.preventDefault();
      const idx = (activeIdx >= 0 ? activeIdx : 0);
      const item = lastSuggestions[idx];
      if (item) pickSuggestion(item);
      return;
    }
  });

  // click afuera
  document.addEventListener('click', (ev) => {
    if (!suggBox.contains(ev.target) && ev.target !== searchInput) hideSuggestions();
  });

  function render() {
    rowsBody.innerHTML = '';

    rows.forEach((r, idx) => {
      const tr = document.createElement('tr');

      const nombre = escapeHtml(r.nombre);
      const kind = escapeHtml(r.kind);
      const rut = escapeHtml(r.rut_plain || '');
      const banco = escapeHtml(r.banco_code || '');
      const cuenta = escapeHtml(r.cuenta || '');
      const glosa = escapeHtml(r.glosa || '');

      tr.innerHTML = `
        <td>
          <div class="fw-semibold">${nombre}</div>
          <div class="text-muted small">${kind}</div>
        </td>
        <td><code>${rut}</code></td>
        <td>${banco}</td>
        <td>${cuenta}</td>
        <td>
          <input type="number" step="0.01" min="0" class="form-control form-control-sm"
                 value="${Number(r.monto)||0}" data-idx="${idx}" data-field="monto">
        </td>
        <td>
          <input type="text" class="form-control form-control-sm"
                 value="${glosa}" data-idx="${idx}" data-field="glosa"
                 placeholder="Glosa por este pago">
        </td>
        <td class="text-end">
          <button type="button" class="btn btn-sm btn-outline-danger" data-del="${idx}">Eliminar</button>
        </td>
      `;

      rowsBody.appendChild(tr);
    });

    // wiring inputs
    rowsBody.querySelectorAll('input[data-idx]').forEach(inp => {
      inp.addEventListener('input', (ev) => {
        const i = Number(ev.target.getAttribute('data-idx'));
        const field = ev.target.getAttribute('data-field');
        if (!rows[i]) return;

        if (field === 'monto') rows[i].monto = Number(ev.target.value || 0);
        if (field === 'glosa') rows[i].glosa = (ev.target.value || '').trim();
        setStats();
      });
    });

    // wiring delete
    rowsBody.querySelectorAll('button[data-del]').forEach(btn => {
      btn.addEventListener('click', () => {
        const i = Number(btn.getAttribute('data-del'));
        rows.splice(i, 1);
        render();
        setStats();
      });
    });

    itemsJson.value = JSON.stringify(rows);
  }

  function addRow() {
    const monto = Number(montoInput.value || 0);

    if (!picked) {
      alert('Selecciona un beneficiario desde las sugerencias.');
      return;
    }
    if (!(monto > 0)) {
      alert('Ingresa un monto mayor a 0.');
      return;
    }

    const row = {
      kind: picked.kind,
      id: picked.id,
      rut_plain: picked.rut_plain || '',
      nombre: picked.nombre || picked.label || '',
      banco_code: picked.banco_code || '',
      cuenta: picked.cuenta || '',
      email: picked.email || 'transferencias@grupo-cs.cl',
      monto: monto,
      glosa: (glosaDefault.value || '').trim()
    };

    rows.push(row);
    render();
    setStats();

    // reset búsqueda
    picked = null;
    searchInput.value = '';
    montoInput.value = '';
    searchInput.focus();
  }

  btnAdd.addEventListener('click', addRow);

  // Enter en monto = agregar
  montoInput.addEventListener('keydown', (ev) => {
    if (ev.key === 'Enter') {
      ev.preventDefault();
      addRow();
    }
  });

  frm.addEventListener('submit', (ev) => {
    if (!rows.length) {
      ev.preventDefault();
      alert('Agrega al menos un registro a la nómina.');
      return;
    }
    itemsJson.value = JSON.stringify(rows);
  });

  // init
  setStats();
})();
