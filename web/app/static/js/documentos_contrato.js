(function () {
  "use strict";

  const page = document.querySelector("[data-docs-contract-page]");
  if (!page) return;

  const searchInput = page.querySelector("[data-doc-search]");
  const filterButtons = Array.from(page.querySelectorAll("[data-doc-filter]"));
  const items = Array.from(page.querySelectorAll("[data-doc-item]"));
  const emptyFilter = page.querySelector("[data-doc-empty-filter]");
  const clearButton = page.querySelector("[data-doc-clear-filters]");

  let activeFilter = "all";

  function normalize(value) {
    return (value || "")
      .toString()
      .normalize("NFD")
      .replace(/[\u0300-\u036f]/g, "")
      .toLowerCase()
      .trim();
  }

  function applyFilters() {
    const query = normalize(searchInput ? searchInput.value : "");
    let visible = 0;

    items.forEach((item) => {
      const type = normalize(item.dataset.docType || "");
      const name = normalize(item.dataset.docName || item.textContent || "");
      const matchesType = activeFilter === "all" || type === activeFilter;
      const matchesQuery = !query || name.includes(query);
      const shouldShow = matchesType && matchesQuery;
      item.classList.toggle("d-none", !shouldShow);
      if (shouldShow) visible += 1;
    });

    if (emptyFilter) {
      emptyFilter.classList.toggle("d-none", visible !== 0 || items.length === 0);
    }
  }

  filterButtons.forEach((button) => {
    button.addEventListener("click", () => {
      activeFilter = normalize(button.dataset.docFilter || "all");
      filterButtons.forEach((btn) => btn.classList.toggle("active", btn === button));
      applyFilters();
    });
  });

  if (searchInput) searchInput.addEventListener("input", applyFilters);

  if (clearButton) {
    clearButton.addEventListener("click", () => {
      activeFilter = "all";
      if (searchInput) searchInput.value = "";
      filterButtons.forEach((btn) => btn.classList.toggle("active", normalize(btn.dataset.docFilter) === "all"));
      applyFilters();
      if (searchInput) searchInput.focus();
    });
  }
})();
