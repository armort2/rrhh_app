(function () {
  const elInicio = document.getElementById("fecha_inicio");
  const elTermino = document.getElementById("fecha_termino");
  const elDias = document.getElementById("dias_habiles");

  if (!elInicio || !elTermino || !elDias) return;

  const parseDate = (s) => {
    if (!s) return null;
    const [y, m, d] = s.split("-").map(Number);
    if (!y || !m || !d) return null;
    return new Date(y, m - 1, d);
  };

  const formatDate = (dt) => {
    const y = dt.getFullYear();
    const m = String(dt.getMonth() + 1).padStart(2, "0");
    const d = String(dt.getDate()).padStart(2, "0");
    return `${y}-${m}-${d}`;
  };

  const feriadosEl = document.getElementById("feriados-data");
  let feriadosArr = [];

  if (feriadosEl) {
    try {
      feriadosArr = JSON.parse(feriadosEl.textContent || "[]");
    } catch (e) {
      feriadosArr = [];
    }
  }

  const feriadosSet = new Set(feriadosArr);

  const toISO = (dt) => {
    const y = dt.getFullYear();
    const m = String(dt.getMonth() + 1).padStart(2, "0");
    const d = String(dt.getDate()).padStart(2, "0");
    return `${y}-${m}-${d}`;
  };

  const isWeekend = (dt) => {
    const day = dt.getDay(); // 0=Dom ... 6=Sáb
    return day === 0 || day === 6;
  };

  const isHoliday = (dt) => {
    return feriadosSet.has(toISO(dt));
  };

  const isNonWorking = (dt) => isWeekend(dt) || isHoliday(dt);

  const addDays = (dt, n) => {
    const copy = new Date(dt);
    copy.setDate(copy.getDate() + n);
    return copy;
  };

  const countBusinessDaysInclusive = (start, end) => {
    if (!start || !end) return 0;
    if (end < start) return 0;
    let n = 0;
    let cur = new Date(start);
    while (cur <= end) {
      if (!isNonWorking(cur)) n++;
      cur = addDays(cur, 1);
    }
    return n;
  };

  const calcEndByBusinessDays = (start, businessDays) => {
    if (!start || !businessDays || businessDays < 1) return null;

    let cur = new Date(start);
    let counted = 0;

    while (true) {
      if (!isNonWorking(cur)) counted++;
      if (counted >= businessDays) return cur;
      cur = addDays(cur, 1);
    }
  };

  const recalcFromDays = () => {
    const start = parseDate(elInicio.value);
    const days = parseInt(elDias.value || "", 10);

    if (!start || !days || days < 1) return;

    const end = calcEndByBusinessDays(start, days);
    if (!end) return;

    elTermino.value = formatDate(end);
  };

  const recalcFromEnd = () => {
    const start = parseDate(elInicio.value);
    const end = parseDate(elTermino.value);

    if (!start || !end) return;

    const days = countBusinessDaysInclusive(start, end);
    if (!days) return;

    elDias.value = String(days);
  };

  elDias.addEventListener("input", () => recalcFromDays());
  elTermino.addEventListener("input", () => recalcFromEnd());

  elInicio.addEventListener("input", () => {
    const hasDays = (elDias.value || "").trim() !== "";
    const hasEnd = (elTermino.value || "").trim() !== "";
    if (hasDays) recalcFromDays();
    else if (hasEnd) recalcFromEnd();
  });

  const init = () => {
    const hasDays = (elDias.value || "").trim() !== "";
    const hasEnd = (elTermino.value || "").trim() !== "";
    if (hasDays) recalcFromDays();
    else if (hasEnd) recalcFromEnd();
  };

  init();
})();
