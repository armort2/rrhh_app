import csv
import sys
from datetime import datetime

from app import create_app, db
from app.models import Trabajador, Obra


def parse_date(value: str):
    if not value:
        return None
    value = value.strip()
    formatos = ["%d-%m-%Y", "%Y-%m-%d", "%d/%m/%Y"]
    for fmt in formatos:
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            continue
    return None


def main(csv_path: str):
    app = create_app()
    with app.app_context():
        print(f"📁 Importando trabajadores desde: {csv_path}")
        creados = 0
        saltados = 0

        with open(csv_path, newline="", encoding="utf-8-sig") as f:
            # Separador típico de Excel en español
            reader = csv.DictReader(f, delimiter=';')

            for row in reader:
                rut = (row.get("RUT") or "").strip()
                if not rut:
                    saltados += 1
                    continue

                # Evitar duplicados por RUT
                if Trabajador.query.filter_by(rut=rut).first():
                    print(f"  - Ya existe trabajador con RUT {rut}, se omite.")
                    saltados += 1
                    continue

                # 👇 Tomar nombre de obra desde la columna "Obra"
                obra_nombre = (row.get("Obra") or "").strip()
                if not obra_nombre:
                    print(f"  - Fila con RUT {rut} sin nombre de Obra, se omite.")
                    saltados += 1
                    continue

                # Buscar obra por nombre exacto (ignorando mayúsculas/minúsculas)
                obra = Obra.query.filter(Obra.nombre.ilike(obra_nombre)).first()
                if not obra:
                    print(f"  - No encontré Obra '{obra_nombre}' para RUT {rut}, se omite.")
                    saltados += 1
                    continue

                nombres = (row.get("Nombres") or "").strip()
                ap_paterno = (row.get("Ap. Paterno") or "").strip()
                ap_materno = (row.get("Ap. Materno") or "").strip()

                fecha_nac = parse_date(row.get("Fecha Nacimiento") or "")
                nacionalidad = (row.get("Nacionalidad") or "").strip() or None

                sexo_raw = (row.get("Sexo") or "").strip().upper()
                if sexo_raw.startswith("M"):
                    sexo = "M"
                elif sexo_raw.startswith("F"):
                    sexo = "F"
                else:
                    sexo = None

                estado_civil = (row.get("Estado Civil") or "").strip() or None

                direccion = (row.get("Dirección Trabajador") or "").strip() or None
                comuna = (row.get("Comuna Trabajador") or "").strip() or None
                telefono = (row.get("Fono") or "").strip() or None
                tel_emerg = (row.get("Fono Emergencia") or "").strip() or None
                correo = (row.get("Correo electrónico") or "").strip() or None

                num_cargas = None  # por ahora sin columna directa

                vigencia = (row.get("Vigencia mes") or "").strip().upper()
                if vigencia == "SI":
                    estado_trabajador = "VIGENTE"
                else:
                    estado_trabajador = "DESVINCULADO"

                tipo_trabajador = None
                fecha_ingreso = None  # lo afinamos después con otra hoja si quieres

                t = Trabajador(
                    rut=rut,
                    nombres=nombres,
                    ap_paterno=ap_paterno,
                    ap_materno=ap_materno,
                    fecha_nacimiento=fecha_nac,
                    nacionalidad=nacionalidad,
                    sexo=sexo,
                    estado_civil=estado_civil,
                    direccion=direccion,
                    comuna=comuna,
                    telefono=telefono,
                    telefono_emergencia=tel_emerg,
                    correo=correo,
                    num_cargas_familiares=num_cargas,
                    estado_trabajador=estado_trabajador,
                    tipo_trabajador=tipo_trabajador,
                    fecha_ingreso_empresa=fecha_ingreso,
                    obra_id=obra.id,
                )

                db.session.add(t)
                creados += 1

        db.session.commit()
        print(f"✔ Importados {creados} trabajadores nuevos.")
        print(f"ℹ Registros saltados (sin RUT / sin Obra / sin Obra en BD / duplicados): {saltados}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Uso: python -m app.import_trabajadores_quintero /app/data/archivo.csv")
        sys.exit(1)
    main(sys.argv[1])
