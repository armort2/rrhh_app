(function () {
  const form = document.getElementById("form-generar-anexo");
  const btn = document.getElementById("btn-generar");
  const sel = document.getElementById("formato");
  const hint = document.getElementById("generando-hint");

  if (!form || !btn) return;

  form.addEventListener("submit", function () {
    btn.disabled = true;
    if (sel) sel.disabled = true;
    if (hint) hint.style.display = "block";

    const original = btn.getAttribute("data-original-text") || btn.textContent;
    btn.textContent = "⏳ Generando…";
    btn.setAttribute("data-original-text", original);
  });
})();
