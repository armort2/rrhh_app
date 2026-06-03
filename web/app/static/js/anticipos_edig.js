document.addEventListener("DOMContentLoaded", () => {
  const btn = document.getElementById("btn-cargar-excluidos");
  if (!btn) return;

  btn.addEventListener("click", async () => {
    const url = btn.dataset.url;
    const cont = document.getElementById("excluidos-container");
    const body = document.getElementById("excluidos-body");

    if (!url || !cont || !body) return;

    btn.disabled = true;
    btn.textContent = "Cargando…";

    try {
      const res = await fetch(url);
      const data = await res.json();

      body.innerHTML = "";
      (data.excluidos || []).forEach((x) => {
        const tr = document.createElement("tr");

        const rut = document.createElement("td");
        rut.textContent = x.rut || "-";

        const nombre = document.createElement("td");
        nombre.textContent = x.nombre || "-";

        const monto = document.createElement("td");
        monto.className = "text-end";
        monto.textContent = (x.monto || 0).toLocaleString("es-CL");

        const motivo = document.createElement("td");
        const badge = document.createElement("span");
        badge.className = "badge bg-warning";
        badge.textContent = x.motivo || "-";
        motivo.appendChild(badge);

        tr.append(rut, nombre, monto, motivo);
        body.appendChild(tr);
      });

      cont.classList.remove("d-none");
      btn.textContent = "Ocultar detalle";
      btn.onclick = () => cont.classList.toggle("d-none");
    } catch (e) {
      alert("No se pudo cargar el detalle de excluidos");
    } finally {
      btn.disabled = false;
    }
  });
});
