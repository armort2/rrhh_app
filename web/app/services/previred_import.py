from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pdfplumber


_MESES = {
    "enero": 1,
    "febrero": 2,
    "marzo": 3,
    "abril": 4,
    "mayo": 5,
    "junio": 6,
    "julio": 7,
    "agosto": 8,
    "septiembre": 9,
    "setiembre": 9,
    "octubre": 10,
    "noviembre": 11,
    "diciembre": 12,
}


def _clean_text(text: str) -> str:
    text = text.replace("\xa0", " ")
    text = re.sub(r"[ \t]+", " ", text)
    return text.strip()


def _money_to_decimal_str(raw: str | None) -> str | None:
    """
    Convierte:
      '39.790,63'   -> '39790.63'
      '69.611'      -> '69611'
      '$ 3.581.157' -> '3581157'
    """
    s = (raw or "").strip()
    if not s:
        return None

    s = s.replace("$", "").replace(" ", "").strip()

    # caso decimal chileno
    if "," in s:
        s = s.replace(".", "").replace(",", ".")
        return s

    # caso entero con miles
    s = s.replace(".", "")
    return s


def _fmt_periodo(year: int, month: int) -> str:
    return f"{year:04d}-{month:02d}"


def _last_day_of_month(year: int, month: int) -> int:
    if month == 2:
        leap = (year % 4 == 0 and (year % 100 != 0 or year % 400 == 0))
        return 29 if leap else 28
    if month in (4, 6, 9, 11):
        return 30
    return 31


def _extract_periodo_from_filename(filename: str) -> tuple[str | None, str | None, str | None]:
    s = (filename or "").lower()

    m = re.search(
        r"(enero|febrero|marzo|abril|mayo|junio|julio|agosto|septiembre|setiembre|octubre|noviembre|diciembre)[-_ ]+(\d{4})",
        s,
        re.IGNORECASE,
    )
    if not m:
        return None, None, None

    mes_txt = m.group(1).lower()
    year = int(m.group(2))
    month = _MESES[mes_txt]

    periodo = _fmt_periodo(year, month)
    desde = f"{year:04d}-{month:02d}-01"
    hasta = f"{year:04d}-{month:02d}-{_last_day_of_month(year, month):02d}"
    return periodo, desde, hasta


def _extract_periodo_from_text(text: str) -> tuple[str | None, str | None, str | None]:
    m = re.search(
        r"remuneraciones\s+(enero|febrero|marzo|abril|mayo|junio|julio|agosto|septiembre|setiembre|octubre|noviembre|diciembre)\s+(\d{4})",
        text,
        re.IGNORECASE,
    )
    if not m:
        m = re.search(
            r"\b(enero|febrero|marzo|abril|mayo|junio|julio|agosto|septiembre|setiembre|octubre|noviembre|diciembre)\s+(\d{4})\b",
            text,
            re.IGNORECASE,
        )

    if not m:
        return None, None, None

    mes_txt = m.group(1).lower()
    year = int(m.group(2))
    month = _MESES[mes_txt]

    periodo = _fmt_periodo(year, month)
    desde = f"{year:04d}-{month:02d}-01"
    hasta = f"{year:04d}-{month:02d}-{_last_day_of_month(year, month):02d}"
    return periodo, desde, hasta


def _extract_first(pattern: str, text: str) -> str | None:
    m = re.search(pattern, text, re.IGNORECASE | re.DOTALL)
    if not m:
        return None
    return m.group(1).strip()


def _find_table_with_text(tables: list[list[list[Any]]], needle: str) -> list[list[Any]] | None:
    needle_low = needle.lower()

    for table in tables:
        joined = "\n".join(
            " | ".join("" if c is None else str(c) for c in row)
            for row in table
        ).lower()
        if needle_low in joined:
            return table

    return None


def _table_to_text(table: list[list[Any]] | None) -> str:
    if not table:
        return ""
    return "\n".join(
        " | ".join("" if c is None else str(c) for c in row)
        for row in table
    )


def _extract_indicadores_from_tables(tables: list[list[list[Any]]]) -> dict:
    data = {
        "uf": None,
        "utm": None,
        "uta": None,
        "tope_imponible_afp": None,
        "tope_imponible_inp": None,
        "tope_imponible_seguro_cesantia": None,
        "renta_minima_dependiente": None,
        "renta_minima_menor_mayor65": None,
        "renta_minima_no_remuneracional": None,
        "renta_minima_casa_particular": None,
    }

    # ---------------------------------------------------------
    # TABLA 1: UF / UTM / UTA
    # ---------------------------------------------------------
    table1 = _find_table_with_text(tables, "Valor UTM UTA")
    if table1:
        t1 = _table_to_text(table1)

        # UF
        m_uf = re.search(
            r"Al\s+\d{1,2}\s+de\s+[A-Za-záéíóúÁÉÍÓÚ]+\s+del\s+\d{4}\s*:\s*\$?\s*([\d\.\,]+)",
            t1,
            re.IGNORECASE,
        )
        if m_uf:
            data["uf"] = _money_to_decimal_str(m_uf.group(1))

        # UTM y UTA desde fila tipo:
        # ... | Febrero 2026 | $ 69.611 $ 835.332
        m_utm_uta = re.search(
            r"(enero|febrero|marzo|abril|mayo|junio|julio|agosto|septiembre|setiembre|octubre|noviembre|diciembre)\s+\d{4}\s*\|\s*\$?\s*([\d\.\,]+)\s+\$?\s*([\d\.\,]+)",
            t1,
            re.IGNORECASE,
        )
        if m_utm_uta:
            data["utm"] = _money_to_decimal_str(m_utm_uta.group(2))
            data["uta"] = _money_to_decimal_str(m_utm_uta.group(3))

    # ---------------------------------------------------------
    # TABLA 2: topes imponibles + rentas mínimas
    # ---------------------------------------------------------
    table2 = _find_table_with_text(tables, "Rentas Topes Imponibles")
    if table2 and len(table2) >= 3:
        # Fila relevante normalmente es la fila 2 (índice 1)
        row = table2[1]

        c0 = str(row[0] or "")
        c1 = str(row[1] or "")
        c2 = str(row[2] or "")
        c3 = str(row[3] or "")

        # Topes imponibles
        topes_vals = [v.strip() for v in c1.splitlines() if v.strip()]
        if len(topes_vals) >= 3:
            data["tope_imponible_afp"] = _money_to_decimal_str(topes_vals[0])
            data["tope_imponible_inp"] = _money_to_decimal_str(topes_vals[1])
            data["tope_imponible_seguro_cesantia"] = _money_to_decimal_str(topes_vals[2])

        # Rentas mínimas
        rentas_vals = [v.strip() for v in c3.splitlines() if v.strip()]
        if len(rentas_vals) >= 3:
            data["renta_minima_dependiente"] = _money_to_decimal_str(rentas_vals[0])
            data["renta_minima_menor_mayor65"] = _money_to_decimal_str(rentas_vals[1])
            data["renta_minima_casa_particular"] = _money_to_decimal_str(rentas_vals[2])

        # Fila siguiente: fines no remuneracionales
        if len(table2) >= 4:
            row2 = table2[2]
            if len(row2) >= 4:
                data["renta_minima_no_remuneracional"] = _money_to_decimal_str(str(row2[3] or ""))

    return data


@dataclass
class PreviredParseResult:
    periodo: str | None
    fecha_vigencia_desde: str | None
    fecha_vigencia_hasta: str | None

    uf: str | None
    utm: str | None
    uta: str | None

    renta_minima_dependiente: str | None
    renta_minima_menor_mayor65: str | None
    renta_minima_no_remuneracional: str | None

    tope_imponible_afp: str | None
    tope_imponible_inp: str | None
    tope_imponible_seguro_cesantia: str | None

    fuente: str
    fuente_documento: str | None
    observaciones: str | None

    raw_text: str

    def to_dict(self) -> dict:
        return {
            "periodo": self.periodo,
            "fecha_vigencia_desde": self.fecha_vigencia_desde,
            "fecha_vigencia_hasta": self.fecha_vigencia_hasta,
            "uf": self.uf,
            "utm": self.utm,
            "uta": self.uta,
            "renta_minima_dependiente": self.renta_minima_dependiente,
            "renta_minima_menor_mayor65": self.renta_minima_menor_mayor65,
            "renta_minima_no_remuneracional": self.renta_minima_no_remuneracional,
            "tope_imponible_afp": self.tope_imponible_afp,
            "tope_imponible_inp": self.tope_imponible_inp,
            "tope_imponible_seguro_cesantia": self.tope_imponible_seguro_cesantia,
            "fuente": self.fuente,
            "fuente_documento": self.fuente_documento,
            "observaciones": self.observaciones,
            "raw_text": self.raw_text,
        }


def parse_previred_pdf(pdf_path: str | Path) -> PreviredParseResult:
    pdf_path = Path(pdf_path)

    if not pdf_path.exists():
        raise FileNotFoundError(f"No existe el archivo: {pdf_path}")

    pages_text: list[str] = []
    all_tables: list[list[list[Any]]] = []

    with pdfplumber.open(str(pdf_path)) as pdf:
        for page in pdf.pages:
            txt = page.extract_text() or ""
            if txt:
                pages_text.append(_clean_text(txt))

            tables = page.extract_tables() or []
            all_tables.extend(tables)

    raw_text = "\n".join(pages_text).strip()
    if not raw_text:
        raise ValueError("No se pudo extraer texto del PDF Previred.")

    # ---------------------------------------------------------
    # Período
    # ---------------------------------------------------------
    periodo, fecha_desde, fecha_hasta = _extract_periodo_from_filename(pdf_path.name)
    if not periodo:
        periodo, fecha_desde, fecha_hasta = _extract_periodo_from_text(raw_text)

    # ---------------------------------------------------------
    # Primero intentamos por tablas (más confiable)
    # ---------------------------------------------------------
    table_data = _extract_indicadores_from_tables(all_tables)

    uf = table_data["uf"]
    utm = table_data["utm"]
    uta = table_data["uta"]

    renta_dep = table_data["renta_minima_dependiente"]
    renta_menor65 = table_data["renta_minima_menor_mayor65"]
    renta_no_rem = table_data["renta_minima_no_remuneracional"]
    renta_casa_part = table_data["renta_minima_casa_particular"]

    tope_afp = table_data["tope_imponible_afp"]
    tope_inp = table_data["tope_imponible_inp"]
    tope_afc = table_data["tope_imponible_seguro_cesantia"]

    # ---------------------------------------------------------
    # Fallbacks desde texto si algo vino vacío
    # ---------------------------------------------------------
    if not uf:
        uf = _money_to_decimal_str(
            _extract_first(
                r"Valor\s+UF.*?Al\s+\d{1,2}\s+de.*?del\s+\d{4}:\s*\$?\s*([\d\.\,]+)",
                raw_text,
            )
        )

    if not renta_dep:
        renta_dep = _money_to_decimal_str(
            _extract_first(r"Trab\.\s*Dependientes\s+e\s+Independientes:\s*\$?\s*([\d\.\,]+)", raw_text)
        )

    if not renta_menor65:
        renta_menor65 = _money_to_decimal_str(
            _extract_first(r"Menores\s+de\s+18\s+y\s+Mayores\s+de\s+65:\s*\$?\s*([\d\.\,]+)", raw_text)
        )

    if not renta_no_rem:
        renta_no_rem = _money_to_decimal_str(
            _extract_first(r"Para\s+fines\s+no\s+remuneracionales:\s*\$?\s*([\d\.\,]+)", raw_text)
        )

    if not tope_afp:
        tope_afp = _money_to_decimal_str(
            _extract_first(r"Para\s+afiliados\s+a\s+una\s+AFP.*?:\s*\$?\s*([\d\.\,]+)", raw_text)
        )

    if not tope_inp:
        tope_inp = _money_to_decimal_str(
            _extract_first(r"Para\s+afiliados\s+al\s+INP.*?:\s*\$?\s*([\d\.\,]+)", raw_text)
        )

    observaciones = None
    if renta_casa_part:
        observaciones = f"PDF Previred informado. Renta mínima trabajador/a casa particular: {renta_casa_part}"

    return PreviredParseResult(
        periodo=periodo,
        fecha_vigencia_desde=fecha_desde,
        fecha_vigencia_hasta=fecha_hasta,
        uf=uf,
        utm=utm,
        uta=uta,
        renta_minima_dependiente=renta_dep,
        renta_minima_menor_mayor65=renta_menor65,
        renta_minima_no_remuneracional=renta_no_rem,
        tope_imponible_afp=tope_afp,
        tope_imponible_inp=tope_inp,
        tope_imponible_seguro_cesantia=tope_afc,
        fuente="PREVIRED",
        fuente_documento=pdf_path.name,
        observaciones=observaciones,
        raw_text=raw_text,
    )