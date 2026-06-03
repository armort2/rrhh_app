document.addEventListener("DOMContentLoaded", () => {
  document.querySelectorAll("[data-select-all]").forEach((master) => {
    master.addEventListener("change", () => {
      const group = master.getAttribute("data-select-all");
      const checks = document.querySelectorAll(`.chk-item[data-group="${group}"]`);
      checks.forEach((chk) => { chk.checked = master.checked; });
    });
  });

  const KEY = "horas_extras_revision_remu_open_worker";

  document.querySelectorAll(".js-open-worker").forEach((btn) => {
    btn.addEventListener("click", () => {
      const wid = btn.getAttribute("data-worker-id") || "";
      if (wid) sessionStorage.setItem(KEY, wid);
    });
  });

  const btnSelection = document.querySelector(".js-open-from-selection");
  if (btnSelection) {
    btnSelection.addEventListener("click", () => {
      const firstChecked = document.querySelector(".chk-item:checked");
      if (firstChecked) {
        const wid = firstChecked.getAttribute("data-worker-id") || "";
        if (wid) sessionStorage.setItem(KEY, wid);
      } else {
        sessionStorage.removeItem(KEY);
      }
    });
  }

  const widToOpen = sessionStorage.getItem(KEY);
  if (widToOpen) {
    const collapseEl = document.querySelector(`[data-worker-collapse="${widToOpen}"]`);
    const headerEl = document.querySelector(`[data-worker-header="${widToOpen}"]`);

    if (collapseEl && window.bootstrap && window.bootstrap.Collapse) {
      document.querySelectorAll("#accordionRevisionRemu .accordion-collapse.show").forEach((openEl) => {
        if (openEl !== collapseEl) {
          const inst = window.bootstrap.Collapse.getOrCreateInstance(openEl, { toggle: false });
          inst.hide();
        }
      });

      const inst = window.bootstrap.Collapse.getOrCreateInstance(collapseEl, { toggle: false });
      inst.show();

      if (headerEl) headerEl.scrollIntoView({ behavior: "smooth", block: "start" });
    }

    sessionStorage.removeItem(KEY);
  }

  const form = document.getElementById("form-revision-remu");
  if (!form) return;

  let locked = false;

  form.addEventListener("submit", (e) => {
    if (locked) {
      e.preventDefault();
      return;
    }

    locked = true;

    const submits = form.querySelectorAll('button[type="submit"], input[type="submit"]');
    submits.forEach((btn) => {
      btn.disabled = true;
      btn.setAttribute("aria-disabled", "true");
    });

    const submitter = e.submitter;
    if (submitter && submitter.classList && submitter.classList.contains("js-submit-loading")) {
      const txt = submitter.getAttribute("data-loading-text") || "Procesando…";
      const icon = submitter.getAttribute("data-loading-icon");

      if (!submitter.dataset.originalHtml) submitter.dataset.originalHtml = submitter.innerHTML;

      let html = "";
      if (icon === "spinner") {
        html += '<span class="spinner-border spinner-border-sm me-2" role="status" aria-hidden="true"></span>';
      }
      html += txt;
      submitter.innerHTML = html;
    }
  });
});
