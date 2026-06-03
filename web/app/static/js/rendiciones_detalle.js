(function () {
  document.addEventListener("DOMContentLoaded", function () {
    const form = document.getElementById("modalEditItemForm");
    const idLabel = document.getElementById("modalEditItemIdLabel");
    const fecha = document.getElementById("modalEditFecha");
    const detalle = document.getElementById("modalEditDetalle");
    const descripcion = document.getElementById("modalEditDescripcion");
    const tipoDoc = document.getElementById("modalEditTipoDoc");
    const nroDoc = document.getElementById("modalEditNroDoc");
    const proveedor = document.getElementById("modalEditProveedor");
    const monto = document.getElementById("modalEditMonto");
    const config = document.getElementById("rendiciones-detalle-config");
    const editUrlTemplate = config?.dataset.editUrlTemplate || "";

    if (!form || !editUrlTemplate) return;

    document.querySelectorAll(".js-btn-editar-item").forEach((btn) => {
      btn.addEventListener("click", function () {
        const itemId = this.getAttribute("data-item-id") || "";

        form.action = editUrlTemplate.replace("/items/0/editar", "/items/" + encodeURIComponent(itemId) + "/editar");
        if (idLabel) idLabel.textContent = itemId;
        if (fecha) fecha.value = this.getAttribute("data-item-fecha") || "";
        if (detalle) detalle.value = this.getAttribute("data-item-detalle") || "";
        if (descripcion) descripcion.value = this.getAttribute("data-item-descripcion") || "";
        if (tipoDoc) tipoDoc.value = this.getAttribute("data-item-tipo-doc") || "";
        if (nroDoc) nroDoc.value = this.getAttribute("data-item-nro-doc") || "";
        if (proveedor) proveedor.value = this.getAttribute("data-item-proveedor") || "";
        if (monto) monto.value = this.getAttribute("data-item-monto") || "";
      });
    });
  });
})();
