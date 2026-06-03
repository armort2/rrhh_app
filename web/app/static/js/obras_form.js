// web/app/static/js/obras_form.js
(function () {
  "use strict";

  document.addEventListener("DOMContentLoaded", function () {
    const estado = document.getElementById("estado");
    const cierre = document.getElementById("fecha_cierre");
    if (!estado || !cierre) return;

    function todayISO() {
      const today = new Date();
      const month = String(today.getMonth() + 1).padStart(2, "0");
      const day = String(today.getDate()).padStart(2, "0");
      return `${today.getFullYear()}-${month}-${day}`;
    }

    estado.addEventListener("change", function () {
      if (estado.value === "CERRADA" && !cierre.value) cierre.value = todayISO();
      if (estado.value === "ACTIVA") cierre.value = "";
    });
  });
})();
