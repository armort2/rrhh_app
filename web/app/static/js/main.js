// web/app/static/js/main.js
(function () {
  "use strict";

  document.addEventListener("DOMContentLoaded", function () {
    initBootstrapTooltips();
    initRevealOnScroll();
    initKpiCounters();
    initDropdownSubmenus();
    initBootstrapValidation();
    initSelectBulkActions();
    initBackToTop();
    initFilterCounters();
    initBusyButtons();
    initConfirmActions();
    initActionSemantics();
    initAutoDismissFlashes();
  });

  function initBootstrapTooltips() {
    if (!window.bootstrap) return;

    document.querySelectorAll('[data-bs-toggle="tooltip"]').forEach(function (el) {
      new window.bootstrap.Tooltip(el);
    });
  }

  function initRevealOnScroll() {
    const items = document.querySelectorAll("[data-animate]");
    if (!items.length) return;

    if (!("IntersectionObserver" in window)) {
      items.forEach(function (el) { el.classList.add("is-visible"); });
      return;
    }

    const observer = new IntersectionObserver(function (entries) {
      entries.forEach(function (entry) {
        if (!entry.isIntersecting) return;
        entry.target.classList.add("is-visible");
        observer.unobserve(entry.target);
      });
    }, { threshold: 0.12 });

    items.forEach(function (el, index) {
      if (!el.style.getPropertyValue("--reveal-delay")) {
        el.style.setProperty("--reveal-delay", Math.min(index * 55, 360) + "ms");
      }
      observer.observe(el);
    });
  }

  function initKpiCounters() {
    const counters = document.querySelectorAll("[data-count-up]");
    if (!counters.length) return;

    const prefersReducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

    counters.forEach(function (el) {
      const endValue = parseInt(el.dataset.countUp || el.textContent || "0", 10);
      if (Number.isNaN(endValue)) return;

      if (prefersReducedMotion || endValue <= 0) {
        el.textContent = endValue.toLocaleString("es-CL");
        return;
      }

      const duration = 750;
      const start = performance.now();

      function tick(now) {
        const progress = Math.min((now - start) / duration, 1);
        const eased = 1 - Math.pow(1 - progress, 3);
        const current = Math.round(endValue * eased);
        el.textContent = current.toLocaleString("es-CL");

        if (progress < 1) requestAnimationFrame(tick);
      }

      requestAnimationFrame(tick);
    });
  }

  function initDropdownSubmenus() {
    document.querySelectorAll(".dropdown-submenu > .dropdown-item").forEach(function (toggle) {
      toggle.addEventListener("click", function (event) {
        event.preventDefault();
        event.stopPropagation();

        const parent = toggle.closest(".dropdown-submenu");
        const menu = parent ? parent.querySelector(":scope > .dropdown-menu") : null;
        if (!parent || !menu) return;

        parent.parentElement.querySelectorAll(":scope > .dropdown-submenu > .dropdown-menu.show").forEach(function (openMenu) {
          if (openMenu !== menu) openMenu.classList.remove("show");
        });

        menu.classList.toggle("show");
        toggle.setAttribute("aria-expanded", menu.classList.contains("show") ? "true" : "false");
      });
    });

    document.querySelectorAll(".topbar .dropdown").forEach(function (dropdown) {
      dropdown.addEventListener("hidden.bs.dropdown", function () {
        dropdown.querySelectorAll(".dropdown-submenu .dropdown-menu.show").forEach(function (menu) {
          menu.classList.remove("show");
        });
        dropdown.querySelectorAll(".dropdown-submenu > .dropdown-item[aria-expanded]").forEach(function (toggle) {
          toggle.setAttribute("aria-expanded", "false");
        });
      });
    });
  }

  function initBootstrapValidation() {
    document.querySelectorAll(".needs-validation").forEach(function (form) {
      form.addEventListener("submit", function (event) {
        if (!form.checkValidity()) {
          event.preventDefault();
          event.stopPropagation();
        }
        form.classList.add("was-validated");
      }, false);
    });
  }

  function initSelectBulkActions() {
    document.querySelectorAll("[data-select-all]").forEach(function (btn) {
      btn.addEventListener("click", function () {
        const selector = btn.getAttribute("data-select-all");
        const select = selector ? document.querySelector(selector) : null;
        if (!select) return;
        Array.from(select.options).forEach(function (option) { option.selected = true; });
      });
    });

    document.querySelectorAll("[data-clear-all]").forEach(function (btn) {
      btn.addEventListener("click", function () {
        const selector = btn.getAttribute("data-clear-all");
        const select = selector ? document.querySelector(selector) : null;
        if (!select) return;
        Array.from(select.options).forEach(function (option) { option.selected = false; });
      });
    });
  }

  function initFilterCounters() {
    document.querySelectorAll("[data-filter-form]").forEach(function (form) {
      const targetSelector = form.getAttribute("data-filter-count-target");
      const target = targetSelector ? document.querySelector(targetSelector) : form.querySelector("[data-filter-count]");
      if (!target) return;

      function hasValue(control) {
        if (!control.name || control.disabled) return false;
        if (["hidden", "submit", "button", "reset"].includes(control.type)) return false;
        if ((control.type === "checkbox" || control.type === "radio")) return control.checked;
        if (control.tagName === "SELECT" && control.multiple) {
          return Array.from(control.options).some(function (option) { return option.selected && option.value !== ""; });
        }
        return String(control.value || "").trim() !== "";
      }

      function sync() {
        const controls = Array.from(form.elements || []);
        const count = controls.filter(hasValue).length;
        target.textContent = count === 1 ? "1 filtro activo" : count + " filtros activos";
        target.classList.toggle("is-empty", count === 0);
      }

      form.addEventListener("input", sync);
      form.addEventListener("change", sync);
      sync();
    });
  }

  function initBusyButtons() {
    document.querySelectorAll("form[data-busy-on-submit]").forEach(function (form) {
      form.addEventListener("submit", function () {
        const button = form.querySelector('[type="submit"]');
        if (!button || button.disabled) return;
        const label = button.getAttribute("data-busy-label") || "Procesando…";
        button.dataset.originalHtml = button.innerHTML;
        button.disabled = true;
        button.innerHTML = '<span class="spinner-border spinner-border-sm me-1" aria-hidden="true"></span>' + label;
      });
    });
  }


  function initConfirmActions() {
    document.querySelectorAll("[data-confirm-message]").forEach(function (el) {
      const eventName = el.tagName === "FORM" ? "submit" : "click";
      el.addEventListener(eventName, function (event) {
        const message = el.getAttribute("data-confirm-message");
        if (!message) return;
        if (!window.confirm(message)) {
          event.preventDefault();
          event.stopPropagation();
        }
      });
    });
  }


  // INICIO UX TRANSVERSAL · ACCIONES Y BOTONES CRÍTICOS
  function initActionSemantics() {
    const actionSelectors = [
      "a.btn",
      "button.btn",
      "input[type='submit'].btn",
      "input[type='button'].btn"
    ];

    document.querySelectorAll(actionSelectors.join(",")).forEach(function (button) {
      if (button.classList.contains("btn-logout")) return;
      button.classList.add("cs-action-btn");

      const text = normalizeActionText(button.textContent || button.value || button.getAttribute("aria-label") || "");
      const href = normalizeActionText(button.getAttribute("href") || "");
      const combined = text + " " + href;

      if (button.classList.contains("btn-danger") || button.classList.contains("btn-outline-danger") || /(eliminar|borrar|deshabilitar|reset|rechazar|anular)/.test(combined)) {
        button.classList.add("cs-action-danger");
        return;
      }

      if (button.classList.contains("btn-success") || button.classList.contains("btn-outline-success") || /(aprobar|habilitar|pagar|confirmar|finalizar)/.test(combined)) {
        button.classList.add("cs-action-success");
        return;
      }

      if (button.classList.contains("btn-warning") || button.classList.contains("btn-outline-warning") || /(advertencia|revisar|pendiente|reabrir)/.test(combined)) {
        button.classList.add("cs-action-warning");
        return;
      }

      if (/(volver|cancelar|limpiar|atras|atrás)/.test(combined)) {
        button.classList.add("cs-action-back");
        return;
      }

      if (/(pdf|docx|word|excel|xlsx|csv|descargar|imprimir|exportar|nomina|nómina)/.test(combined)) {
        button.classList.add("cs-action-document");
        return;
      }

      if (button.classList.contains("btn-primary") || /(nuevo|crear|guardar|generar|regenerar|editar|actualizar|emitir|registrar)/.test(combined)) {
        button.classList.add("cs-action-primary");
        return;
      }

      if (button.classList.contains("btn-info") || button.classList.contains("btn-outline-info") || /(ver|detalle|ficha|buscar|consultar)/.test(combined)) {
        button.classList.add("cs-action-info");
        return;
      }

      button.classList.add("cs-action-secondary");
    });
  }

  function normalizeActionText(value) {
    return String(value || "")
      .toLowerCase()
      .normalize("NFD")
      .replace(/[\u0300-\u036f]/g, "")
      .replace(/\s+/g, " ")
      .trim();
  }
  // FIN UX TRANSVERSAL · ACCIONES Y BOTONES CRÍTICOS


  function initAutoDismissFlashes() {
    document.querySelectorAll(".cs-flash-message[data-auto-dismiss]").forEach(function (alertEl) {
      const duration = parseInt(alertEl.getAttribute("data-auto-dismiss") || "8000", 10);
      if (!duration || Number.isNaN(duration) || duration < 1000) return;

      alertEl.style.setProperty("--cs-flash-duration", duration + "ms");

      window.setTimeout(function () {
        alertEl.classList.add("is-hiding");

        window.setTimeout(function () {
          if (window.bootstrap && window.bootstrap.Alert) {
            const instance = window.bootstrap.Alert.getOrCreateInstance(alertEl);
            instance.close();
          } else {
            alertEl.remove();
          }
        }, 280);
      }, duration);
    });
  }

  function initBackToTop() {
    const button = document.querySelector("[data-back-to-top]");
    if (!button) return;

    function syncVisibility() {
      button.classList.toggle("is-visible", window.scrollY > 420);
    }

    button.addEventListener("click", function () {
      window.scrollTo({ top: 0, behavior: "smooth" });
    });

    syncVisibility();
    window.addEventListener("scroll", syncVisibility, { passive: true });
  }

})();

// Mejora UX transversal para formularios: marca campos obligatorios y resalta la sección activa.
(function () {
  const formPages = document.querySelectorAll('.cs-form-page');
  if (!formPages.length) return;

  formPages.forEach((page) => {
    page.querySelectorAll('[required]').forEach((field) => {
      if (!field.id) return;
      let label = null;
      try {
        label = page.querySelector(`label[for="${field.id.replace(/"/g, '\\"')}"]`);
      } catch (error) {
        label = null;
      }
      if (label) label.classList.add('cs-required-label');
    });
  });

  document.addEventListener('focusin', (event) => {
    const section = event.target.closest('.cs-form-page form > .mb-4, .cs-form-page .form-section, .cs-form-page .cs-form-section');
    if (section) section.classList.add('cs-section-active');
  });

  document.addEventListener('focusout', (event) => {
    const section = event.target.closest('.cs-form-page form > .mb-4, .cs-form-page .form-section, .cs-form-page .cs-form-section');
    if (!section) return;
    window.setTimeout(() => {
      if (!section.contains(document.activeElement)) {
        section.classList.remove('cs-section-active');
      }
    }, 0);
  });
})();
