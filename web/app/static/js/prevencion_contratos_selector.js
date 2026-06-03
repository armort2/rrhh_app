// web/app/static/js/prevencion_contratos_selector.js
(function () {
  "use strict";

  document.addEventListener("DOMContentLoaded", function () {
    document.querySelectorAll("[data-prevencion-contrato-selector]").forEach(initSelector);
  });

  function initSelector(root) {
    const apiUrl = root.dataset.apiUrl;
    const mode = root.dataset.mode || "single";
    const searchInput = root.querySelector("[data-contrato-search]");
    const resultsBox = root.querySelector("[data-contrato-results]");

    if (!apiUrl || !searchInput || !resultsBox) return;

    let timer = null;

    searchInput.addEventListener("input", function () {
      const q = searchInput.value.trim();
      clearTimeout(timer);

      if (q.length < 2) {
        resultsBox.classList.add("d-none");
        return;
      }

      timer = setTimeout(function () {
        fetch(apiUrl + "?q=" + encodeURIComponent(q))
          .then(function (response) { return response.json(); })
          .then(function (data) { renderResults(root, data.items || [], mode); })
          .catch(function () {
            resultsBox.innerHTML = '<div class="list-group-item text-danger">No fue posible buscar contratos.</div>';
            resultsBox.classList.remove("d-none");
          });
      }, 250);
    });

    if (mode === "multiple") {
      bindRemoveButtons(root);
      refreshEmptyState(root);
    }
  }

  function renderResults(root, items, mode) {
    const resultsBox = root.querySelector("[data-contrato-results]");
    resultsBox.innerHTML = "";

    if (!items.length) {
      resultsBox.innerHTML = '<div class="list-group-item text-muted">Sin resultados.</div>';
      resultsBox.classList.remove("d-none");
      return;
    }

    items.forEach(function (item) {
      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = "list-group-item list-group-item-action";
      btn.innerHTML = renderResultItem(item);
      btn.addEventListener("click", function () {
        if (mode === "multiple") addContrato(root, item);
        else selectContrato(root, item);
      });
      resultsBox.appendChild(btn);
    });

    resultsBox.classList.remove("d-none");
  }

  function renderResultItem(item) {
    return '<div class="fw-semibold">' + escapeHtml(item.trabajador_nombre || "") + '</div>' +
      '<div class="small text-muted">RUT ' + escapeHtml(item.trabajador_rut || "-") +
      ' · Contrato #' + escapeHtml(String(item.contrato_id || "")) +
      ' · ' + escapeHtml(item.cargo_nombre || "Sin cargo") +
      ' · ' + escapeHtml(item.obra_nombre || "Sin obra") + '</div>';
  }

  function selectContrato(root, item) {
    const contratoInput = root.querySelector('[name="contrato_id"]');
    const trabajadorInput = root.querySelector('[name="trabajador_id"]');
    const obraInput = root.querySelector('[name="obra_id"]');
    const selectedBox = root.querySelector("[data-contrato-selected]");
    const resultsBox = root.querySelector("[data-contrato-results]");
    const searchInput = root.querySelector("[data-contrato-search]");

    if (contratoInput) contratoInput.value = item.contrato_id || "";
    if (trabajadorInput) trabajadorInput.value = item.trabajador_id || "";
    if (obraInput) obraInput.value = item.obra_id || "";

    if (selectedBox) {
      selectedBox.innerHTML = '<div class="fw-semibold">' + escapeHtml(item.trabajador_nombre || "") + '</div>' +
        '<div class="small text-muted">Contrato #' + escapeHtml(String(item.contrato_id || "")) +
        ' · ' + escapeHtml(item.cargo_nombre || "Sin cargo") +
        ' · ' + escapeHtml(item.obra_nombre || "Sin obra") + '</div>' +
        '<div class="small text-muted">' + escapeHtml(item.trabajador_rut || "") + '</div>';
    }

    resultsBox.classList.add("d-none");
    searchInput.value = "";
  }

  function addContrato(root, item) {
    const selectedBox = root.querySelector("[data-contratos-selected]");
    const emptySelected = root.querySelector("[data-empty-selected]");
    const resultsBox = root.querySelector("[data-contrato-results]");
    const searchInput = root.querySelector("[data-contrato-search]");

    if (!selectedBox || alreadySelected(selectedBox, item.contrato_id)) {
      resultsBox.classList.add("d-none");
      searchInput.value = "";
      return;
    }

    const div = document.createElement("div");
    div.className = "selected-contract border rounded-3 p-2 bg-white mb-2";
    div.dataset.id = item.contrato_id;
    div.innerHTML = '\n      <input type="hidden" name="contrato_ids" value="' + escapeHtml(String(item.contrato_id || "")) + '">\n      <div class="d-flex justify-content-between gap-2">\n        <div>\n          <div class="fw-semibold">' + escapeHtml(item.trabajador_nombre || "") + '</div>\n          <div class="small text-muted">Contrato #' + escapeHtml(String(item.contrato_id || "")) + ' · ' + escapeHtml(item.cargo_nombre || "Sin cargo") + ' · ' + escapeHtml(item.obra_nombre || "Sin obra") + '</div>\n          <div class="small text-muted">' + escapeHtml(item.trabajador_rut || "") + '</div>\n        </div>\n        <button type="button" class="btn btn-sm btn-outline-danger js-remove-contract">Quitar</button>\n      </div>\n    ';

    selectedBox.insertBefore(div, emptySelected || null);
    bindRemoveButtons(root);
    refreshEmptyState(root);
    resultsBox.classList.add("d-none");
    searchInput.value = "";
  }

  function alreadySelected(selectedBox, id) {
    return !!selectedBox.querySelector('.selected-contract[data-id="' + String(id) + '"]');
  }

  function bindRemoveButtons(root) {
    root.querySelectorAll(".js-remove-contract").forEach(function (btn) {
      btn.onclick = function () {
        btn.closest(".selected-contract").remove();
        refreshEmptyState(root);
      };
    });
  }

  function refreshEmptyState(root) {
    const selectedBox = root.querySelector("[data-contratos-selected]");
    const emptySelected = root.querySelector("[data-empty-selected]");
    if (!selectedBox || !emptySelected) return;
    const selected = selectedBox.querySelectorAll(".selected-contract");
    emptySelected.classList.toggle("d-none", selected.length > 0);
  }

  function escapeHtml(value) {
    return String(value)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/\"/g, "&quot;")
      .replace(/'/g, "&#039;");
  }
})();
