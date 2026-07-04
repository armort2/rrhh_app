from __future__ import annotations

import unittest

from flask import Flask

from app.common.navigation import safe_next_url


class NavigationSmokeTest(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)

    def test_safe_next_url_permite_ruta_interna_relativa(self):
        with self.app.test_request_context("/contratos/1?next=/trabajadores/2"):
            self.assertEqual(safe_next_url("/trabajadores/2"), "/trabajadores/2")

    def test_safe_next_url_bloquea_url_externa(self):
        with self.app.test_request_context("/contratos/1"):
            self.assertEqual(safe_next_url("https://malicioso.example/path", fallback="/inicio"), "/inicio")


if __name__ == "__main__":
    unittest.main()
