# web/app/services/bank_nominas.py
from __future__ import annotations

import os
import re
from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Dict, Iterable, List, Optional, Tuple

from openpyxl import load_workbook
from openpyxl.workbook.workbook import Workbook


# ============================
# Constantes / Plantillas
# ============================

TEMPLATE_PAGOS_REMUN = "santander_pagos_masivos_remuneraciones.xlsx"
TEMPLATE_TRANSFER_MAS = "santander_transferencias_masivas.xlsx"


MESES_ES = [
    "",  # 0 (no usado)
    "Enero",
    "Febrero",
    "Marzo",
    "Abril",
    "Mayo",
    "Junio",
    "Julio",
    "Agosto",
    "Septiembre",
    "Octubre",
    "Noviembre",
    "Diciembre",
]


def periodo_label_es(anio: int, mes: int) -> str:
    mes_txt = MESES_ES[mes] if 1 <= mes <= 12 else f"Mes {mes}"
    return f"{mes_txt} {anio}"


def glosa_anticipo(anio: int, mes: int) -> str:
    return f"Anticipo de sueldo - {periodo_label_es(anio, mes)}"


# ============================
# Normalización RUT (banco)
# ============================

def rut_plain_from_parts(rut: str | None, dv: str | None) -> str | None:
    """
    Retorna RUT para banco: sin puntos, sin guión, con DV, DV en mayúscula.
    Ej: rut="11.399.975", dv="6" => "113999756"
    """
    if not rut:
        return None
    base = re.sub(r"[^0-9]", "", str(rut))
    if not base:
        return None
    d = (dv or "").strip().upper()
    if not d:
        # Si viene "rut" ya con DV pegado, lo dejamos como está (limpio)
        # pero en tu modelo normalmente viene separado.
        return base
    return f"{base}{d}"


def rut_plain_from_str(rut_completo: str | None) -> str | None:
    """
    Soporta entradas tipo:
      - 11.399.975-6
      - 11399975-6
      - 113999756
      - 22334254K
    Retorna: 113999756 / 22334254K
    """
    if not rut_completo:
        return None
    s = str(rut_completo).strip().upper().replace(".", "").replace(" ", "")
    if not s:
        return None
    if "-" in s:
        base, dv = s.split("-", 1)
        base = re.sub(r"[^0-9]", "", base)
        dv = re.sub(r"[^0-9K]", "", dv)
        return f"{base}{dv}" if base and dv else None
    # Sin guion: asumimos último char es DV si es K o dígito y el resto numérico
    # Si ya viene todo numérico (DV numérico), igual sirve.
    return re.sub(r"[^0-9K]", "", s) or None


# ============================
# DTO filas bancarias
# ============================

@dataclass(frozen=True)
class BankRow:
    rut_beneficiario: str
    nombre_beneficiario: str
    monto: Decimal
    codigo_banco: str
    cuenta_destino: str
    email_beneficiario: str


@dataclass(frozen=True)
class BuildResult:
    ok_rows: List[BankRow]
    excluidos: List[Dict[str, Any]]  # {detalle_id, trabajador_id, motivo, ...}


# ============================
# Validaciones / construcción
# ============================

def _clean_str(v: Any) -> str:
    return (str(v).strip() if v is not None else "")


def _to_decimal(v: Any) -> Decimal:
    try:
        if v is None:
            return Decimal("0")
        if isinstance(v, Decimal):
            return v
        return Decimal(str(v))
    except Exception:
        return Decimal("0")


def _is_valid_bank_code(code: str) -> bool:
    # Santander suele aceptar código numérico (SBIF/CMF). Tu banco.codigo_sbif es string.
    c = _clean_str(code)
    return bool(c) and bool(re.fullmatch(r"\d{1,10}", c))


def _is_valid_account(acc: str) -> bool:
    a = _clean_str(acc)
    # cuentas pueden tener guiones en algunos bancos, pero normalmente es numérica.
    # Dejamos solo dígitos para exportar (más estable en cargadores).
    return bool(re.sub(r"\D", "", a))


def _account_plain(acc: str) -> str:
    return re.sub(r"\D", "", _clean_str(acc))


def _email_or_fallback(email: str | None) -> str:
    e = _clean_str(email)
    return e if e else "transferencias@grupo-cs.cl"


def build_bank_rows(
    detalles_rows: Iterable[Tuple[Any, Any, Any]],  # (AnticipoDetalle, Trabajador, Banco)
) -> BuildResult:
    """
    Recibe tuplas: (AnticipoDetalle, Trabajador, BancoBeneficiario)
    y construye filas válidas para exportación bancaria.
    Respeta pago a tercero si está activo.
    """
    ok: List[BankRow] = []
    excluidos: List[Dict[str, Any]] = []

    for det, t, banco in detalles_rows:
        monto = _to_decimal(getattr(det, "monto", None))

        if monto <= 0:
            excluidos.append(
                {
                    "detalle_id": getattr(det, "id", None),
                    "trabajador_id": getattr(det, "trabajador_id", None),
                    "motivo": "Monto <= 0",
                    "rut": getattr(det, "rut", None),
                    "nombre": getattr(det, "nombre_completo", None),
                }
            )
            continue

        # Beneficiario: tercero o trabajador
        tercero = bool(getattr(t, "pago_tercero_activo", False))

        if tercero:
            rut_b = rut_plain_from_str(getattr(t, "pago_tercero_rut", None))
            nombre_b = _clean_str(getattr(t, "pago_tercero_nombre", None))
            cuenta_b = _account_plain(getattr(t, "pago_tercero_cuenta_numero", None))
            banco_code = _clean_str(getattr(getattr(t, "pago_tercero_banco", None), "codigo_sbif", None))
            email_b = _email_or_fallback(getattr(t, "correo", None))
        else:
            rut_b = rut_plain_from_parts(getattr(t, "rut", None), getattr(t, "dv", None))
            # Nombre completo “apellido paterno + apellido materno + nombres” (como usas en pantalla)
            nombre_b = " ".join(
                p for p in [
                    _clean_str(getattr(t, "ap_paterno", None)),
                    _clean_str(getattr(t, "ap_materno", None)),
                    _clean_str(getattr(t, "nombres", None)),
                ] if p
            ).strip()
            # Cuenta: prioriza cuenta_numero; fallback a cuenta_rut
            cuenta_raw = _clean_str(getattr(t, "cuenta_numero", None)) or _clean_str(getattr(t, "cuenta_rut", None))
            cuenta_b = _account_plain(cuenta_raw)
            banco_code = _clean_str(getattr(banco, "codigo_sbif", None))
            email_b = _email_or_fallback(getattr(t, "correo", None))

        # Validaciones
        if not rut_b:
            excluidos.append(
                {
                    "detalle_id": getattr(det, "id", None),
                    "trabajador_id": getattr(det, "trabajador_id", None),
                    "motivo": "RUT beneficiario vacío/invalidable",
                    "nombre": nombre_b or getattr(det, "nombre_completo", None),
                }
            )
            continue

        if not nombre_b:
            excluidos.append(
                {
                    "detalle_id": getattr(det, "id", None),
                    "trabajador_id": getattr(det, "trabajador_id", None),
                    "motivo": "Nombre beneficiario vacío",
                    "rut_beneficiario": rut_b,
                }
            )
            continue

        if not _is_valid_bank_code(banco_code):
            excluidos.append(
                {
                    "detalle_id": getattr(det, "id", None),
                    "trabajador_id": getattr(det, "trabajador_id", None),
                    "motivo": f"Código banco inválido: {banco_code or '(vacío)'}",
                    "rut_beneficiario": rut_b,
                    "nombre": nombre_b,
                }
            )
            continue

        if not _is_valid_account(cuenta_b):
            excluidos.append(
                {
                    "detalle_id": getattr(det, "id", None),
                    "trabajador_id": getattr(det, "trabajador_id", None),
                    "motivo": "Cuenta destino inválida/vacía",
                    "rut_beneficiario": rut_b,
                    "nombre": nombre_b,
                }
            )
            continue

        ok.append(
            BankRow(
                rut_beneficiario=rut_b,
                nombre_beneficiario=nombre_b,
                monto=monto,
                codigo_banco=banco_code,
                cuenta_destino=cuenta_b,
                email_beneficiario=email_b,
            )
        )

    return BuildResult(ok_rows=ok, excluidos=excluidos)


def aggregate_rows(rows: List[BankRow]) -> List[BankRow]:
    """
    Agrega por (rut, banco, cuenta). Evita duplicados que a veces complican el cargador.
    Conserva nombre/email del primer registro.
    """
    acc: Dict[Tuple[str, str, str], BankRow] = {}
    sums: Dict[Tuple[str, str, str], Decimal] = {}

    for r in rows:
        k = (r.rut_beneficiario, r.codigo_banco, r.cuenta_destino)
        if k not in acc:
            acc[k] = r
            sums[k] = r.monto
        else:
            sums[k] = sums[k] + r.monto

    out: List[BankRow] = []
    for k, base in acc.items():
        out.append(
            BankRow(
                rut_beneficiario=base.rut_beneficiario,
                nombre_beneficiario=base.nombre_beneficiario,
                monto=sums[k],
                codigo_banco=base.codigo_banco,
                cuenta_destino=base.cuenta_destino,
                email_beneficiario=base.email_beneficiario,
            )
        )
    return out


# ============================
# Escritura XLSX desde plantilla
# ============================

def _norm_header(s: str) -> str:
    # Normalización simple y estable (sin dependencias externas)
    s = _clean_str(s).lower()
    s = s.replace("á", "a").replace("é", "e").replace("í", "i").replace("ó", "o").replace("ú", "u")
    s = re.sub(r"\s+", " ", s)
    return s.strip()


def _header_map(ws) -> Dict[str, int]:
    """
    Mapea encabezados (fila 1) a índice de columna (1-based).
    """
    m: Dict[str, int] = {}
    for col in range(1, ws.max_column + 1):
        v = ws.cell(row=1, column=col).value
        if v is None:
            continue
        m[_norm_header(v)] = col
    return m


def _clear_data_rows(ws, start_row: int = 2) -> None:
    """
    Limpia filas de datos (valores) manteniendo formatos.
    """
    max_row = ws.max_row
    max_col = ws.max_column
    if max_row < start_row:
        return
    for r in range(start_row, max_row + 1):
        for c in range(1, max_col + 1):
            ws.cell(row=r, column=c).value = None


def build_xlsx_from_template(
    template_path: str,
    template_kind: str,  # "PAGOS_REMUN" | "TRANSFER_MAS"
    rows: List[BankRow],
    anio: int,
    mes: int,
) -> Workbook:
    wb = load_workbook(template_path)
    ws = wb.active

    headers = _header_map(ws)
    _clear_data_rows(ws, start_row=2)

    glosa = glosa_anticipo(anio, mes)

    if template_kind == "PAGOS_REMUN":
        # Headers esperados (normalizados)
        # RUT Beneficiario | Nombre Beneficiario | Monto | Código Banco | Cuenta destino |
        # Modalidad de pago | Sucursal entrega | Mail beneficiario | Glosa mail
        def col(name: str) -> int:
            key = _norm_header(name)
            if key not in headers:
                raise ValueError(f"Plantilla inválida: no se encontró columna '{name}'.")
            return headers[key]

        c_rut = col("RUT Beneficiario")
        c_nom = col("Nombre Beneficiario")
        c_monto = col("Monto")
        c_banco = col("Código Banco")
        c_cta = col("Cuenta destino")
        c_mod = col("Modalidad de pago")
        c_suc = col("Sucursal entrega")
        c_mail = col("Mail beneficiario")
        c_glosa = col("Glosa mail")

        for i, r in enumerate(rows, start=2):
            ws.cell(row=i, column=c_rut).value = r.rut_beneficiario
            ws.cell(row=i, column=c_nom).value = r.nombre_beneficiario
            ws.cell(row=i, column=c_monto).value = float(r.monto)
            ws.cell(row=i, column=c_banco).value = r.codigo_banco
            ws.cell(row=i, column=c_cta).value = r.cuenta_destino
            ws.cell(row=i, column=c_mod).value = "3"
            ws.cell(row=i, column=c_suc).value = "999"
            ws.cell(row=i, column=c_mail).value = r.email_beneficiario or "transferencias@grupo-cs.cl"
            ws.cell(row=i, column=c_glosa).value = glosa

        return wb

    if template_kind == "TRANSFER_MAS":
        # Cuenta Origen | Moneda | Cuenta destino | Moneda2 | Codigo Banco | Rut Beneficiario |
        # Nombre Beneficiario | Monto | Glosa | Direccion correo | Glosa correo |
        # Glosa cartola cliente | Glosa Cartola Beneficiario
        def col(name: str) -> int:
            key = _norm_header(name)
            if key not in headers:
                raise ValueError(f"Plantilla inválida: no se encontró columna '{name}'.")
            return headers[key]

        c_origen = col("Cuenta Origen")
        c_mon1 = col("Moneda")
        c_cta = col("Cuenta destino")
        c_mon2 = col("Moneda2")
        c_banco = col("Codigo Banco")
        c_rut = col("Rut Beneficiario")
        c_nom = col("Nombre Beneficiario")
        c_monto = col("Monto")
        c_glosa = col("Glosa")
        c_mail = col("Direccion correo")
        c_glosa_mail = col("Glosa correo")
        c_cart_cli = col("Glosa cartola cliente")
        c_cart_ben = col("Glosa Cartola Beneficiario")

        for i, r in enumerate(rows, start=2):
            ws.cell(row=i, column=c_origen).value = "5555555555"
            ws.cell(row=i, column=c_mon1).value = "CLP"
            ws.cell(row=i, column=c_cta).value = r.cuenta_destino
            ws.cell(row=i, column=c_mon2).value = "CLP"
            ws.cell(row=i, column=c_banco).value = r.codigo_banco
            ws.cell(row=i, column=c_rut).value = r.rut_beneficiario
            ws.cell(row=i, column=c_nom).value = r.nombre_beneficiario
            ws.cell(row=i, column=c_monto).value = float(r.monto)
            ws.cell(row=i, column=c_glosa).value = glosa
            ws.cell(row=i, column=c_mail).value = r.email_beneficiario or "transferencias@grupo-cs.cl"
            ws.cell(row=i, column=c_glosa_mail).value = glosa
            ws.cell(row=i, column=c_cart_cli).value = glosa
            ws.cell(row=i, column=c_cart_ben).value = glosa

        return wb

    raise ValueError(f"template_kind inválido: {template_kind}")


def get_template_path(app_root_path: str, template_filename: str) -> str:
    return os.path.join(app_root_path, "static", "xlsx_templates", template_filename)
