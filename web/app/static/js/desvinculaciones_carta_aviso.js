(function () {
  function getSelectedPresetText() {
    const sel = document.getElementById("CAUSAL_8_PRESET_KEY");
    if (!sel) return "";
    const opt = sel.options[sel.selectedIndex];
    if (!opt) return "";
    return (opt.getAttribute("data-text") || "").trim();
  }

  function replaceText() {
    const t = getSelectedPresetText();
    if (!t) return;
    const ta = document.getElementById("CAUSAL_8_FRASE");
    if (!ta) return;
    ta.value = t;
    ta.focus();
  }

  function appendText() {
    const t = getSelectedPresetText();
    if (!t) return;
    const ta = document.getElementById("CAUSAL_8_FRASE");
    if (!ta) return;
    const cur = (ta.value || "").trim();
    ta.value = cur ? (cur + "\n\n" + t) : t;
    ta.focus();
  }

  const btnR = document.getElementById("btnPresetReplace");
  const btnA = document.getElementById("btnPresetAppend");
  if (btnR) btnR.addEventListener("click", replaceText);
  if (btnA) btnA.addEventListener("click", appendText);

  // Bonus: si hay preset seleccionado y textarea está vacío -> autoinserta.
  const sel = document.getElementById("CAUSAL_8_PRESET_KEY");
  const ta = document.getElementById("CAUSAL_8_FRASE");
  if (sel && ta) {
    sel.addEventListener("change", function () {
      const t = getSelectedPresetText();
      if (!t) return;
      if (!(ta.value || "").trim()) {
        ta.value = t;
      }
    });
  }
})();
