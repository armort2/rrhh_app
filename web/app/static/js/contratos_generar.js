// web/app/static/js/contratos_generar.js
(function () {
  "use strict";

  document.addEventListener("DOMContentLoaded", function () {
    const formato = document.getElementById("formato");
    const badge = document.getElementById("preview_formato_badge");
    if (!formato || !badge) return;

    const labels = {
      DOCX: "DOCX",
      PDF: "PDF",
      AMBOS: "DOCX + PDF"
    };

    function refreshPreviewFormato() {
      badge.textContent = labels[formato.value] || formato.value || "DOCX";
    }

    formato.addEventListener("change", refreshPreviewFormato);
    refreshPreviewFormato();
  });
})();
