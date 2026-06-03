# web/app/services/num_to_words_es.py
from __future__ import annotations

from decimal import Decimal


_UNIDADES = [
    "cero","uno","dos","tres","cuatro","cinco","seis","siete","ocho","nueve",
    "diez","once","doce","trece","catorce","quince","dieciséis","diecisiete","dieciocho","diecinueve"
]
_DECENAS = ["", "", "veinte","treinta","cuarenta","cincuenta","sesenta","setenta","ochenta","noventa"]
_CIENTOS = ["", "ciento","doscientos","trescientos","cuatrocientos","quinientos","seiscientos","setecientos","ochocientos","novecientos"]


def _menos_de_100(n: int) -> str:
    if n < 20:
        return _UNIDADES[n]
    if n < 30:
        if n == 20:
            return "veinte"
        return "veinti" + _UNIDADES[n - 20]
    d = n // 10
    r = n % 10
    if r == 0:
        return _DECENAS[d]
    return f"{_DECENAS[d]} y {_UNIDADES[r]}"


def _menos_de_1000(n: int) -> str:
    if n == 0:
        return "cero"
    if n == 100:
        return "cien"
    c = n // 100
    r = n % 100
    if c == 0:
        return _menos_de_100(r)
    if r == 0:
        return _CIENTOS[c]
    return f"{_CIENTOS[c]} {_menos_de_100(r)}"


def _numero_a_palabras(n: int) -> str:
    if n < 1000:
        return _menos_de_1000(n)

    if n < 1_000_000:
        miles = n // 1000
        resto = n % 1000
        pref = "mil" if miles == 1 else f"{_menos_de_1000(miles)} mil"
        return pref if resto == 0 else f"{pref} {_menos_de_1000(resto)}"

    if n < 1_000_000_000:
        mill = n // 1_000_000
        resto = n % 1_000_000
        pref = "un millón" if mill == 1 else f"{_menos_de_1000(mill)} millones"
        return pref if resto == 0 else f"{pref} {_numero_a_palabras(resto)}"

    return str(n)


def clp_a_palabras(monto: Decimal | int | str | None) -> str:
    """
    Convierte a texto CLP (sin centavos, porque en nómina normalmente es entero).
    Ej: 100000 -> 'cien mil pesos'
    """
    if monto is None:
        return ""

    if isinstance(monto, Decimal):
        n = int(monto.quantize(Decimal("1")))
    else:
        n = int(Decimal(str(monto)).quantize(Decimal("1")))

    palabras = _numero_a_palabras(abs(n))
    suf = "peso" if abs(n) == 1 else "pesos"
    if n < 0:
        return f"menos {palabras} {suf}"
    return f"{palabras} {suf}"