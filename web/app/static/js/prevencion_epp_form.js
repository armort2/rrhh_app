// web/app/static/js/prevencion_epp_form.js
(function () {
  "use strict";

  document.addEventListener("DOMContentLoaded", function () {
    const table = document.getElementById("tablaEppItems");
    const btn = document.getElementById("btnAddEpp");
    if (!table || !btn) return;

    function bindRemoveButtons() {
      table.querySelectorAll(".js-remove-row").forEach(function (button) {
        button.onclick = function () {
          const rows = table.querySelectorAll("tbody tr");
          if (rows.length <= 1) return;
          button.closest("tr").remove();
        };
      });
    }

    btn.addEventListener("click", function () {
      const tbody = table.querySelector("tbody");
      const firstRow = tbody.querySelector("tr");
      const clone = firstRow.cloneNode(true);

      clone.querySelectorAll("input").forEach(function (input) {
        input.value = input.type === "number" ? "1" : "";
      });

      clone.querySelectorAll("select").forEach(function (select) {
        select.selectedIndex = 0;
      });

      tbody.appendChild(clone);
      bindRemoveButtons();
    });

    bindRemoveButtons();
  });
})();
