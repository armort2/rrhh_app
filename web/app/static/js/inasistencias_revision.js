// web/app/static/js/inasistencias_revision.js
(function () {
  "use strict";

  document.addEventListener("DOMContentLoaded", function () {
    initSelectAllByWorker();
    initAccordionMemory();
    initSubmitFeedback();
  });

  function initSelectAllByWorker() {
    document.querySelectorAll("[data-select-all]").forEach(function (master) {
      master.addEventListener("change", function () {
        const group = master.getAttribute("data-select-all");
        document.querySelectorAll(`.chk-item[data-group="${group}"]`).forEach(function (chk) {
          chk.checked = master.checked;
        });
      });
    });
  }

  function initAccordionMemory() {
    const key = "inasistencias_revision_open_worker";

    document.querySelectorAll(".js-open-worker").forEach(function (btn) {
      btn.addEventListener("click", function () {
        const workerId = btn.getAttribute("data-worker-id") || "";
        if (workerId) sessionStorage.setItem(key, workerId);
      });
    });

    const btnSelection = document.querySelector(".js-open-from-selection");
    if (btnSelection) {
      btnSelection.addEventListener("click", function () {
        const firstChecked = document.querySelector(".chk-item:checked");
        const workerId = firstChecked ? (firstChecked.getAttribute("data-worker-id") || "") : "";

        if (workerId) sessionStorage.setItem(key, workerId);
        else sessionStorage.removeItem(key);
      });
    }

    const workerIdToOpen = sessionStorage.getItem(key);
    if (!workerIdToOpen) return;

    const collapseEl = document.querySelector(`[data-worker-collapse="${workerIdToOpen}"]`);
    const headerEl = document.querySelector(`[data-worker-header="${workerIdToOpen}"]`);

    if (collapseEl && window.bootstrap && window.bootstrap.Collapse) {
      document.querySelectorAll("#accordionRevision .accordion-collapse.show").forEach(function (openEl) {
        if (openEl !== collapseEl) {
          window.bootstrap.Collapse.getOrCreateInstance(openEl, { toggle: false }).hide();
        }
      });

      window.bootstrap.Collapse.getOrCreateInstance(collapseEl, { toggle: false }).show();
      if (headerEl) headerEl.scrollIntoView({ behavior: "smooth", block: "start" });
    }

    sessionStorage.removeItem(key);
  }

  function initSubmitFeedback() {
    const form = document.getElementById("form-revision");
    if (!form) return;

    let locked = false;

    form.addEventListener("submit", function (event) {
      if (locked) {
        event.preventDefault();
        return;
      }

      locked = true;
      form.querySelectorAll('button[type="submit"], input[type="submit"]').forEach(function (btn) {
        btn.disabled = true;
        btn.setAttribute("aria-disabled", "true");
      });

      const submitter = event.submitter;
      if (!submitter || !submitter.classList || !submitter.classList.contains("js-submit-loading")) return;

      const text = submitter.getAttribute("data-loading-text") || "Procesando…";
      const icon = submitter.getAttribute("data-loading-icon");

      if (!submitter.dataset.originalHtml) submitter.dataset.originalHtml = submitter.innerHTML;

      let html = "";
      if (icon === "spinner") {
        html += '<span class="spinner-border spinner-border-sm me-2" role="status" aria-hidden="true"></span>';
      }
      html += text;

      submitter.innerHTML = html;
    });
  }
})();
