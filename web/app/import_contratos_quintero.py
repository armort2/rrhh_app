import csv
import sys
from datetime import datetime
from decimal import Decimal, InvalidOperation

from app import create_app, db
from app.models import Trabajador, Obra, Empleador, Cargo, Contrato


def _norm(text: str) -> str:
    """Normaliza cadenas para compararlas (nombre obra, empleador, cargo)."""
    if not text:
        return ""
    return " ".join(text.strip().lower().split())


def _parse_date(value: str):
    """
    Convierte fechas tipo 'DD-MM-YYYY' o 'YYYY-MM-DD' a date.
    Devuelve None si viene vacía o con formato inválido.
    """
    if not value:
        return None
    value = value.strip()
    if not value:
        return None

    for fmt in ("%d-%m-%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            continue
    print(f"⚠ Fecha inválida: '{value}' -> se deja en None")
    return None


def _parse_int(value: str):
    if not value:
        return None
    value = value.replace(".", "").replace(",", "").strip()
    if not value:
        return None
    try:
        return int(value)
    except ValueError:
        print(f"⚠ Valor entero inválido: '{value}' -> se deja en None")
        return None


def _parse_decimal(value: str):
    if not value:
        return None
    value = value.replace(".", "").replace(",", ".").strip()
    if not value:
        return None
    try:
        return Decimal(value)
    except (InvalidOperation, ValueError):
        print(f"⚠ Valor decimal inválido: '{value}' -> se deja en None")
        return None


def main(csv_path: str):
    app = create_app()
    with app.app_context():
        print(f"📁 Importando CONTRATOS desde: {csv_path}")

        # ---------- Pre-cargar diccionarios de referencia ----------
        trabajadores_por_rut = {
            (t.rut or "").strip(): t
            for t in Trabajador.query.all()
        }

        obras_por_nombre = {
            _norm(o.nombre): o
            for o in Obra.query.all()
        }

        empleadores_por_nombre = {
            _norm(e.razon_social): e
            for e in Empleador.query.all()
        }

        cargos_por_nombre = {
            _norm(c.nombre): c
            for c in Cargo.query.all()
        }

        print(f"👷 Trabajadores en BD : {len(trabajadores_por_rut)}")
        print(f"🏗  Obras en BD        : {len(obras_por_nombre)}")
        print(f"🏢 Empleadores en BD  : {len(empleadores_por_nombre)}")
        print(f"🧱 Cargos en BD       : {len(cargos_por_nombre)}")

        creados = 0
        saltados = 0
        fila_n = 0

        try:
            f = open(csv_path, newline="", encoding="utf-8-sig")
        except FileNotFoundError:
            print(f"❌ No se encontró el archivo CSV en: {csv_path}")
            return

        with f:
            reader = csv.DictReader(f, delimiter=";")
            for row in reader:
                fila_n += 1
                rut = (row.get("RUT") or "").strip()
                obra_nombre = row.get("OBRA") or row.get("Obra") or ""
                empleador_nombre = row.get("EMPLEADOR") or row.get("Empleador") or ""
                cargo_nombre = row.get("CARGO") or row.get("Cargo") or ""
                tipo_contrato = (row.get("TIPO_CONTRATO") or row.get("Tipo Contrato") or "").strip()

                if not rut:
                    print(f"⚠ Fila {fila_n}: sin RUT -> contrato saltado.")
                    saltados += 1
                    continue

                trab = trabajadores_por_rut.get(rut)
                if not trab:
                    print(f"⚠ Fila {fila_n}: no encontré trabajador con RUT '{rut}' -> contrato saltado.")
                    saltados += 1
                    continue

                obra = obras_por_nombre.get(_norm(obra_nombre))
                if not obra:
                    print(f"⚠ Fila {fila_n}: no encontré OBRA '{obra_nombre}' -> contrato saltado.")
                    saltados += 1
                    continue

                empleador = empleadores_por_nombre.get(_norm(empleador_nombre))
                if not empleador:
                    print(f"⚠ Fila {fila_n}: no encontré EMPLEADOR '{empleador_nombre}' -> contrato saltado.")
                    saltados += 1
                    continue

                cargo = cargos_por_nombre.get(_norm(cargo_nombre))
                if not cargo:
                    print(f"⚠ Fila {fila_n}: no encontré CARGO '{cargo_nombre}' -> contrato saltado.")
                    saltados += 1
                    continue

                if not tipo_contrato:
                    print(f"⚠ Fila {fila_n}: sin TIPO_CONTRATO -> contrato saltado.")
                    saltados += 1
                    continue

                # ---------- Parseo de campos ----------
                fecha_inicio = _parse_date(row.get("FECHA_INICIO") or row.get("Fecha Inicio") or "")
                fecha_termino = _parse_date(row.get("FECHA_TERMINO") or row.get("Fecha Término") or "")
                jornada = (row.get("JORNADA") or row.get("Jornada") or "").strip()
                horas_semanales = _parse_int(row.get("HORAS_SEMANALES") or row.get("Horas Semanales") or "")

                sueldo_base = _parse_decimal(row.get("SUELDO_BASE") or row.get("Sueldo Base") or "")
                asig_mov = _parse_decimal(row.get("ASIG_MOVILIZACION") or row.get("Asignación Movilización") or "")
                asig_col = _parse_decimal(row.get("ASIG_COLACION") or row.get("Asignación Colación") or "")
                asig_herra = _parse_decimal(row.get("ASIG_HERRAMIENTAS") or row.get("Asignación Herramientas") or "")

                estado_contrato = (row.get("ESTADO_CONTRATO") or row.get("Estado Contrato") or "VIGENTE").strip().upper()
                causal_termino = (row.get("CAUSAL_TERMINO") or row.get("Causal Término") or "").strip()
                fecha_finiquito = _parse_date(row.get("FECHA_FINIQUITO") or row.get("Fecha Finiquito") or "")

                contrato = Contrato(
                    trabajador_id=trab.id,
                    empleador_id=empleador.id,
                    obra_id=obra.id,
                    cargo_id=cargo.id,
                    tipo_contrato=tipo_contrato,
                    fecha_inicio=fecha_inicio,
                    fecha_termino=fecha_termino,
                    jornada=jornada,
                    horas_semanales=horas_semanales,
                    sueldo_base=sueldo_base,
                    asignacion_movilizacion=asig_mov,
                    asignacion_colacion=asig_col,
                    asignacion_herramientas=asig_herra,
                    estado_contrato=estado_contrato or "VIGENTE",
                    causal_termino=causal_termino or None,
                    fecha_finiquito=fecha_finiquito,
                )

                db.session.add(contrato)
                creados += 1

        db.session.commit()
        print("========================================")
        print(f"✔ Contratos creados       : {creados}")
        print(f"⚠ Contratos saltados      : {saltados}")
        print(f"📄 Filas procesadas (CSV) : {fila_n}")
        print("========================================")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Uso: python -m app.import_contratos_quintero /ruta/al/archivo.csv")
        sys.exit(1)
    main(sys.argv[1])
