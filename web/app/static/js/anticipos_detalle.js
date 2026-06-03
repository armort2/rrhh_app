(function () {
  const selectCargos = document.getElementById("cargo_ids");
  const btnTodos = document.getElementById("btn-seleccionar-todos-cargos");
  const btnLimpiar = document.getElementById("btn-limpiar-cargos");

  if (!selectCargos) return;

  if (btnTodos) {
    btnTodos.addEventListener("click", function () {
      Array.from(selectCargos.options).forEach(function (opt) {
        opt.selected = true;
      });
    });
  }

  if (btnLimpiar) {
    btnLimpiar.addEventListener("click", function () {
      Array.from(selectCargos.options).forEach(function (opt) {
        opt.selected = false;
      });
    });
  }
})();
