from __future__ import annotations

import unittest
from datetime import date
from decimal import Decimal
from types import SimpleNamespace

from app.services import finiquitos_calc as calc


def _contrato(sueldo_base=570000, colacion=0, movilizacion=0):
    return SimpleNamespace(
        sueldo_base=sueldo_base,
        asignacion_colacion=colacion,
        asignacion_movilizacion=movilizacion,
    )


class FiniquitosCalcSmokeTest(unittest.TestCase):
    def test_diff_ymd_inclusivo_control_un_dia(self):
        self.assertEqual(calc.diff_ymd_inclusivo(date(2026, 3, 16), date(2026, 6, 24)), (0, 3, 9))

    def test_promedio_variables_formato_chileno(self):
        self.assertEqual(calc.promedio_variables("100.000", "200000", "300.000"), Decimal("200000.00"))

    def test_base_feriado_variable_suma_sueldo_base_mas_promedio(self):
        base = calc.base_feriado(
            contrato=_contrato(sueldo_base=570000),
            tipo_remuneracion="VARIABLE",
            promedio_variable=Decimal("61500"),
        )
        self.assertEqual(base["sueldo_base"], Decimal("570000.00"))
        self.assertEqual(base["promedio_variable"], Decimal("61500.00"))
        self.assertEqual(base["total"], Decimal("631500.00"))

    def test_engine_version_existe(self):
        self.assertTrue(calc.FINIQUITO_ENGINE_VERSION.startswith("finiquitos_v"))


if __name__ == "__main__":
    unittest.main()
