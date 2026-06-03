# web/app/services/extras_csv.py
from __future__ import annotations

import csv
import os
import re
import tempfile
import zipfile
from decimal import Decimal
from typing import Iterable, Tuple


def _periodo_str(lote) -> str:
    # preferimos el helper/propiedad del modelo si existe
    s = getattr(lote, "periodo_str", None)
    if s:
        return str(s)
    anio = int(getattr(lote, "anio", 0) or 0)
    mes = int(getattr(lote, "mes", 0) or 0)
    return f"{anio:04d}-{mes:02d}"


def _safe_filename(s: str) -> str:
    s = (s or "").strip()
    if not s:
        return "SIN_NOMBRE"
    # limpieza conservadora para Windows/Linux
    s = re.sub(r"[\\/:*?\"<>|]+", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def _clp_int(v) -> int:
    try:
        return int(Decimal(str(v or 0)).quantize(Decimal("1")))
    except Exception:
        try:
            return int(v)
        except Exception:
            return 0


def _nombre_trabajador(t) -> str:
    ap_pat = (getattr(t, "ap_paterno", "") or "").strip()
    ap_mat = (getattr(t, "ap_materno", "") or "").strip()
    noms = (getattr(t, "nombres", "") or "").strip()
    # Formato requerido: <Ap. Paterno> <Ap. Materno> <Nombres>
    return " ".join(x for x in [ap_pat, ap_mat, noms] if x)


def _codigo_haber_edig(item) -> str:
    # Mapeo pedido:
    # BONO => HBONO
    # TRATO => HTRATO
    # Jornadas extraordinarias (SABADO / HORAS_EXTRA) => HJOREXT
    tipo = (getattr(item, "concepto_tipo", "") or "").strip().upper()
    if tipo == "TRATO":
        return "HTRATO"
    if tipo == "JORNADA_EXTRAORDINARIA":
        return "HJOREXT"
    # todo lo demás lo tratamos como bono/haber genérico
    return "HBONO"


def _empleador_display(item) -> str:
    """
    Nombre oficial de empresa para archivo: Empleador.razon_social
    (fallbacks conservadores por si viene nulo).
    """
    emp = getattr(item, "empleador", None)

    # Si el item no trae relación cargada, intentamos por contrato
    if emp is None:
        c = getattr(item, "contrato", None)
        emp = getattr(c, "empleador", None) if c else None

    # Fuente de verdad
    rs = (getattr(emp, "razon_social", None) or "").strip() if emp else ""
    if rs:
        return rs

    # Fallbacks (solo para datos incompletos)
    emp_id = getattr(item, "empleador_id", None)
    if emp_id:
        return f"EMPLEADOR_{emp_id}"

    return "EMPLEADOR_DESCONOCIDO"


def _iter_items(lote) -> Iterable:
    # lote.items ya lo estás usando en templates
    return (getattr(lote, "items", None) or [])



def _contrato_id_item(item) -> int | None:
    cid = getattr(item, "contrato_id", None)
    if cid:
        try:
            return int(cid)
        except Exception:
            return None
    c = getattr(item, "contrato", None)
    cid = getattr(c, "id", None) if c else None
    try:
        return int(cid) if cid else None
    except Exception:
        return None


def _build_nros_contrato_edig_items(items: Iterable) -> dict[int, int]:
    """
    Numeración EDIG por trabajador + empleador dentro del lote de extras.
    Mantiene separadas las asignaciones cuando un trabajador tiene más de un contrato.
    """
    grupos: dict[tuple[int, str], list] = {}
    for it in items:
        cid = _contrato_id_item(it)
        if not cid:
            continue
        t = getattr(it, "trabajador", None)
        tid = int(getattr(t, "id", 0) or getattr(it, "trabajador_id", 0) or 0)
        emp_name = _empleador_display(it)
        if not tid:
            continue
        grupos.setdefault((tid, emp_name), []).append(getattr(it, "contrato", None) or it)

    out: dict[int, int] = {}
    for _key, contratos in grupos.items():
        únicos = {}
        for c in contratos:
            cid = int(getattr(c, "id", None) or getattr(c, "contrato_id", None) or 0)
            if cid:
                únicos[cid] = c
        ordenados = sorted(
            únicos.values(),
            key=lambda c: (str(getattr(c, "fecha_inicio", "") or ""), int(getattr(c, "id", None) or getattr(c, "contrato_id", 0) or 0)),
        )
        for idx, c in enumerate(ordenados, start=1):
            cid = int(getattr(c, "id", None) or getattr(c, "contrato_id", None) or 0)
            if cid:
                out[cid] = idx
    return out

def export_csv_lote(lote) -> Tuple[str, str, str]:
    """
    Retorna: (path_archivo, nombre_descarga, mimetype)
    - Si hay 1 empleador => CSV
    - Si hay N empleadores => ZIP con N CSV
    """
    periodo = _periodo_str(lote)
    cc = (getattr(lote, "centro_costo", "") or "").strip().upper() or "CC"

    items_lote = list(_iter_items(lote))
    nro_contrato_por_id = _build_nros_contrato_edig_items(items_lote)

    # 1) Agregación: (empleador_key, trabajador_id, contrato_id, codigo_edig) => suma_monto
    # además guardamos refs para rut/nombre. La clave incluye contrato_id para no mezclar
    # asignaciones de un mismo trabajador cuando tiene doble contrato.
    agg: dict[tuple[str, int, int, str], dict] = {}

    for it in items_lote:
        t = getattr(it, "trabajador", None)
        if not t:
            continue

        emp_name = _empleador_display(it)
        codigo = _codigo_haber_edig(it)

        contrato_id = _contrato_id_item(it) or 0
        nro_contrato = nro_contrato_por_id.get(contrato_id, 1)

        key = (emp_name, int(getattr(t, "id", 0) or 0), int(contrato_id or 0), codigo)

        if key not in agg:
            agg[key] = {
                "rut": (getattr(t, "rut_completo", "") or "").strip(),
                "nombre": _nombre_trabajador(t),
                "monto": 0,
                "emp_name": emp_name,
                "contrato_id": contrato_id,
                "nro_contrato": nro_contrato,
            }

        agg[key]["monto"] += _clp_int(getattr(it, "monto", 0))

    # Si no hay nada, igual generamos CSV vacío con header (control interno)
    # 2) Partimos por empleador
    por_emp: dict[str, list[dict]] = {}
    for (emp_name, _tid, _cid, _cod), row in agg.items():
        por_emp.setdefault(emp_name, []).append(row)

    # Orden "bonito": por nombre trabajador y luego por código EDIG
    def _sort_key(r: dict):
        return (r.get("nombre") or "", r.get("rut") or "", r.get("monto") or 0)

    for emp_name, rows in por_emp.items():
        rows.sort(key=_sort_key)

    # 3) Generación archivos
    tmpdir = tempfile.mkdtemp(prefix="extras_csv_")

    header = [
        "RUT",
        "Nombre Trabajador",
        "Nro. Contrato",
        "Codigo de Haber o Dscto.",
        "Monto",
        "",  # columna en blanco requerida por EDIG según tus ejemplos
        "Tipo de Fórmula",
        "Código de Fórmula",
    ]

    def _write_csv(path: str, rows: list[dict]) -> None:
        with open(path, "w", encoding="utf-8-sig", newline="") as f:
            w = csv.writer(f, delimiter=";", lineterminator="\r\n")
            w.writerow(header)
            for r in rows:
                monto = int(r.get("monto") or 0)
                if monto <= 0:
                    continue
                rut = (r.get("rut") or "").strip()
                if not rut:
                    continue
                
                w.writerow([
                    rut or "",
                    r.get("nombre") or "",
                    r.get("nro_contrato") or 1, # Nro. Contrato EDIG según contrato del ítem
                    r.get("codigo") or "",     # lo seteamos abajo
                    monto,
                    "",                        # columna vacía
                    "E",
                    "1",
                ])

    # si no hay filas, generamos un CSV “vacío” por consistencia
    if not por_emp:
        emp_name = "SIN_REGISTROS"
        csv_name = f"{periodo} Extras {emp_name} - {cc}.csv"
        csv_path = os.path.join(tmpdir, _safe_filename(csv_name))
        _write_csv(csv_path, [])
        return csv_path, csv_name, "text/csv"

    # generamos CSV por empleador
    csv_files: list[tuple[str, str]] = []
    for emp_name, rows in por_emp.items():
        # convertir rows => agregar código por fila (HBONO/HTRATO/HJOREXT)
        # OJO: en agg key el código está afuera, acá lo recomponemos:
        enriched: list[dict] = []
        for (k_emp, _tid, _cid, cod), base in agg.items():
            if k_emp != emp_name:
                continue
            r = dict(base)
            r["codigo"] = cod
            enriched.append(r)

        # orden final: por rut y código para que EDIG quede estable
        enriched.sort(key=lambda r: (r.get("rut") or "", r.get("codigo") or ""))

        csv_name = f"{periodo} Extras {_safe_filename(emp_name)} - {cc}.csv"
        csv_path = os.path.join(tmpdir, csv_name)
        _write_csv(csv_path, enriched)
        csv_files.append((csv_path, csv_name))

    # 4) Si hay 1 CSV, devolvemos ese CSV. Si hay varios, devolvemos ZIP.
    if len(csv_files) == 1:
        p, n = csv_files[0]
        return p, n, "text/csv"

    zip_name = f"{periodo} Extras - {cc}.zip"
    zip_path = os.path.join(tmpdir, zip_name)
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as z:
        for p, n in csv_files:
            # en el zip guardamos solo el nombre del CSV (sin rutas)
            z.write(p, arcname=n)

    return zip_path, zip_name, "application/zip"