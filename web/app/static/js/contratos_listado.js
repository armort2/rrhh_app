(function () {
  const form = document.getElementById("form-filtros-contratos");
  const inicioDesde = document.getElementById("inicio_desde");
  const inicioHasta = document.getElementById("inicio_hasta");
  const terminoDesde = document.getElementById("termino_desde");
  const terminoHasta = document.getElementById("termino_hasta");

  function pad2(n) {
    return String(n).padStart(2, "0");
  }

  function toISODate(date) {
    return `${date.getFullYear()}-${pad2(date.getMonth() + 1)}-${pad2(date.getDate())}`;
  }

  function firstDayOfMonth(date) {
    return new Date(date.getFullYear(), date.getMonth(), 1);
  }

  function lastDayOfMonth(date) {
    return new Date(date.getFullYear(), date.getMonth() + 1, 0);
  }

  function addDays(date, days) {
    const copy = new Date(date);
    copy.setDate(copy.getDate() + days);
    return copy;
  }

  function getTargets(target) {
    if (target === "termino") return { desde: terminoDesde, hasta: terminoHasta };
    return { desde: inicioDesde, hasta: inicioHasta };
  }

  document.querySelectorAll("[data-select-all]").forEach((btn) => {
    btn.addEventListener("click", () => {
      const selector = btn.getAttribute("data-select-all");
      const select = selector ? document.querySelector(selector) : null;
      if (!select) return;
      Array.from(select.options).forEach((option) => {
        option.selected = true;
      });
    });
  });

  document.querySelectorAll("[data-clear-all]").forEach((btn) => {
    btn.addEventListener("click", () => {
      const selector = btn.getAttribute("data-clear-all");
      const select = selector ? document.querySelector(selector) : null;
      if (!select) return;
      Array.from(select.options).forEach((option) => {
        option.selected = false;
      });
    });
  });

  document.querySelectorAll("[data-range]").forEach((btn) => {
    btn.addEventListener("click", () => {
      if (!form) return;

      const now = new Date();
      const action = btn.getAttribute("data-range");
      const target = btn.getAttribute("data-target") || "inicio";
      const fields = getTargets(target);

      if (!fields.desde || !fields.hasta) return;

      if (action === "this-month") {
        fields.desde.value = toISODate(firstDayOfMonth(now));
        fields.hasta.value = toISODate(lastDayOfMonth(now));
        form.submit();
        return;
      }

      if (action === "prev-month") {
        const prev = new Date(now.getFullYear(), now.getMonth() - 1, 1);
        fields.desde.value = toISODate(firstDayOfMonth(prev));
        fields.hasta.value = toISODate(lastDayOfMonth(prev));
        form.submit();
        return;
      }

      if (action === "ytd") {
        fields.desde.value = toISODate(new Date(now.getFullYear(), 0, 1));
        fields.hasta.value = toISODate(new Date(now.getFullYear(), 11, 31));
        form.submit();
        return;
      }

      if (action === "next-7") {
        fields.desde.value = toISODate(now);
        fields.hasta.value = toISODate(addDays(now, 7));
        form.submit();
        return;
      }

      if (action === "next-15") {
        fields.desde.value = toISODate(now);
        fields.hasta.value = toISODate(addDays(now, 15));
        form.submit();
        return;
      }

      if (action === "next-30") {
        fields.desde.value = toISODate(now);
        fields.hasta.value = toISODate(addDays(now, 30));
        form.submit();
        return;
      }

      if (action === "clear-dates") {
        fields.desde.value = "";
        fields.hasta.value = "";
        form.submit();
      }
    });
  });
})();
