// web/app/static/js/rendiciones_nueva.js
(function () {
  "use strict";

  document.addEventListener("DOMContentLoaded", function () {
    const form = document.getElementById("formNuevaRendicion");
    const btn = document.getElementById("btnCrearRendicion");
    if (!form || !btn) return;

    let locked = false;

    form.addEventListener("submit", function (event) {
      if (locked) {
        event.preventDefault();
        return false;
      }

      locked = true;
      btn.disabled = true;
      btn.classList.remove("btn-primary");
      btn.classList.add("btn-secondary");
      btn.setAttribute("data-original-html", btn.innerHTML);
      btn.innerHTML = '<span class="spinner-border spinner-border-sm me-2" role="status" aria-hidden="true"></span>Creando rendición…';
      return true;
    });
  });
})();
