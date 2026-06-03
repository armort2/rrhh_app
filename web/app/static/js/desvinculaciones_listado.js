(function () {
  const hiddenMonth = document.getElementById("mes");
  const year = document.getElementById("mes_year");
  const month = document.getElementById("mes_month");

  function syncHiddenMonth() {
    if (!hiddenMonth || !year || !month) return;

    const y = (year.value || "").trim();
    const m = (month.value || "").trim();
    hiddenMonth.value = y && m ? `${y}-${m}` : "";
  }

  if (year && month) {
    year.addEventListener("change", syncHiddenMonth);
    month.addEventListener("change", syncHiddenMonth);
    syncHiddenMonth();
  }
})();
