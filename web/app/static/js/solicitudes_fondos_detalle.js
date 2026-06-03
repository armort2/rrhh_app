(function () {
  function parseIdFromValue(value) {
    const v = (value || "").trim();
    if (!v) return "";

    const first = v.split(" - ")[0];
    const id = parseInt(first, 10);
    if (!id || String(id) !== first) return "";

    return String(id);
  }

  function bindDatalistInput(input) {
    const hiddenId = input.getAttribute("data-target-hidden");
    const errorId = input.getAttribute("data-error-target");
    const hidden = document.getElementById(hiddenId);
    const error = errorId ? document.getElementById(errorId) : null;

    if (!hidden) return;

    function clear() {
      hidden.value = "";
      if (error) error.style.display = "none";
    }

    function sync() {
      const id = parseIdFromValue(input.value);
      if (!id) {
        clear();
        return;
      }

      hidden.value = id;
      if (error) error.style.display = "none";
    }

    input.addEventListener("change", sync);
    input.addEventListener("blur", sync);
    input.addEventListener("input", function () {
      if (!(input.value || "").trim()) clear();
    });
  }

  document.addEventListener("DOMContentLoaded", function () {
    document.querySelectorAll("input.js-datalist[data-target-hidden]").forEach(bindDatalistInput);
  });
})();
