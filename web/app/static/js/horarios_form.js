(function () {
  function getDiaOptions() {
    const dataEl = document.getElementById("horario-dia-options");
    if (!dataEl) return {};
    try {
      return JSON.parse(dataEl.textContent || "{}");
    } catch (error) {
      console.warn("No fue posible leer los días del horario.", error);
      return {};
    }
  }

  function buildDiaSelect(options) {
    const select = document.createElement("select");
    select.name = "tramos_dia";
    select.className = "form-select";

    Object.entries(options).forEach(([value, label]) => {
      const option = document.createElement("option");
      option.value = value;
      option.textContent = label;
      select.appendChild(option);
    });

    return select;
  }

  function bindDeleteButtons() {
    document.querySelectorAll(".btn-del").forEach((btn) => {
      btn.onclick = () => {
        const row = btn.closest("tr");
        if (row) row.remove();
      };
    });
  }

  document.addEventListener("DOMContentLoaded", function () {
    const tableBody = document.querySelector("#tabla-tramos tbody");
    const btnAdd = document.getElementById("btn-add-tramo");
    const diaOptions = getDiaOptions();

    if (btnAdd && tableBody) {
      btnAdd.addEventListener("click", () => {
        const row = document.createElement("tr");

        const tdDia = document.createElement("td");
        tdDia.appendChild(buildDiaSelect(diaOptions));

        row.innerHTML = `
          <td><input class="form-control" type="time" name="tramos_inicio" value=""></td>
          <td><input class="form-control" type="time" name="tramos_termino" value=""></td>
          <td><input class="form-control" type="number" name="tramos_orden" min="1" value="1"></td>
          <td class="text-end"><button type="button" class="btn btn-sm btn-outline-danger btn-del">Quitar</button></td>
        `;
        row.insertBefore(tdDia, row.firstChild);
        tableBody.appendChild(row);
        bindDeleteButtons();
      });
    }

    bindDeleteButtons();
  });
})();
