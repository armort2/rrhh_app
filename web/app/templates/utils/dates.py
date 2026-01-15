from datetime import date

MESES_ES = {
    1: "enero", 2: "febrero", 3: "marzo", 4: "abril",
    5: "mayo", 6: "junio", 7: "julio", 8: "agosto",
    9: "septiembre", 10: "octubre", 11: "noviembre", 12: "diciembre",
}

def fecha_larga_es(fecha: date | None) -> str:
    if not fecha:
        return ""
    return f"{fecha.day} de {MESES_ES[fecha.month]} de {fecha.year}"
