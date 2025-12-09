import csv
from datetime import datetime

import click
from flask.cli import with_appcontext

from .extensions import db
from .models import Trabajador, Banco, Cargo


def _parse_date(value: str):
    """Convierte un string de fecha a objeto date, o None si viene vacío."""
    if not value:
        return None
    value = value.strip()
    if not value:
        return None

    for fmt in ("%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y"):
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            continue
    return None


@click.command("import-trabajadores")
@click.argument("csv_path")
@with_appcontext
def import_trabajadores(csv_path):
    """
    Importa o actualiza trabajadores desde un archivo CSV.

    Uso:
        flask import-trabajadores /app/data/trabajadores_quintero.csv
    """
    click.echo(f"📥 Importando trabajadores desde: {csv_path}")

    count_new = 0
    count_updated = 0

    with open(csv_path, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)

        for row in reader:
            rut = (row.get("rut") or "").strip()
            dv = (row.get("dv") or "").strip()

            if not rut:
                click.echo("⚠️ Fila sin RUT, se omite.")
                continue

            # Buscar trabajador existente por RUT
            trab = Trabajador.query.filter_by(rut=rut).first()

            if trab is None:
                trab = Trabajador(rut=rut, dv=dv or None)
                db.session.add(trab)
                count_new += 1
                modo = "CREADO"
            else:
                modo = "ACTUALIZADO"
                count_updated += 1

            def set_if_empty(attr, value):
                v = value.strip() if isinstance(value, str) else value
                if v == "":
                    v = None
                # Solo rellenamos si está vacío en BD y tenemos un valor no vacío
                if getattr(trab, attr, None) in (None, "", " ") and v not in (None, "", " "):
                    setattr(trab, attr, v)

            # Campos que SÍ existen en Trabajador
            set_if_empty("nombres",       row.get("nombres", ""))
            set_if_empty("ap_paterno",    row.get("ap_paterno", ""))
            set_if_empty("ap_materno",    row.get("ap_materno", ""))
            set_if_empty("direccion",     row.get("direccion", ""))
            set_if_empty("comuna",        row.get("comuna", ""))
            set_if_empty("estado_civil",  row.get("estado_civil", ""))
            set_if_empty("sexo",          row.get("sexo", ""))
            set_if_empty("telefono",      row.get("telefono", ""))
            set_if_empty("telefono_emergencia", row.get("telefono_emergencia", ""))
            set_if_empty("correo",        row.get("correo", ""))
            set_if_empty("nacionalidad",  row.get("nacionalidad", ""))

            # Estado trabajador (si no tiene nada, usamos el del CSV o VIGENTE)
            estado_trabajador = (row.get("estado_trabajador") or "").strip()
            if not estado_trabajador:
                estado_trabajador = "VIGENTE"
            if not getattr(trab, "estado_trabajador", None):
                trab.estado_trabajador = estado_trabajador

            # Fecha de nacimiento
            fecha_nac_str = row.get("fecha_nacimiento")
            if fecha_nac_str and getattr(trab, "fecha_nacimiento", None) is None:
                trab.fecha_nacimiento = _parse_date(fecha_nac_str)

            # Número de cuenta bancaria (mapear desde numero_cta_bancaria → cuenta_numero)
            num_cta = (row.get("numero_cta_bancaria") or "").strip()
            if num_cta and not getattr(trab, "cuenta_numero", None):
                trab.cuenta_numero = num_cta

            # Banco: usamos el nombre del banco del CSV para enlazar a la tabla bancos
            banco_nombre = (row.get("banco") or "").strip()
            if banco_nombre and trab.banco is None:
                banco = Banco.query.filter_by(nombre=banco_nombre).first()
                if banco:
                    trab.banco = banco
                else:
                    click.echo(f"⚠️ Banco no encontrado: '{banco_nombre}' (RUT {rut})")

            click.echo(f" - {modo}: {rut} {trab.nombres or ''} {trab.ap_paterno or ''}")

    db.session.commit()
    click.echo(f"✅ Importación finalizada. Nuevos: {count_new}, Actualizados: {count_updated}")

@click.command("import-cargos")
@click.argument("csv_path")
@with_appcontext
def import_cargos(csv_path):
    """
    Importa o actualiza la tabla de CARGOS desde un CSV con columnas:
    id,nombre
    """
    click.echo(f"🧩 Importando cargos desde: {csv_path}")

    count_new = 0
    count_updated = 0

    with open(csv_path, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)

        for row in reader:
            try:
                cargo_id = int(row.get("id"))
            except (TypeError, ValueError):
                click.echo(f"⚠️ Fila con id inválido: {row.get('id')}, se omite.")
                continue

            nombre = (row.get("nombre") or "").strip()
            if not nombre:
                click.echo(f"⚠️ Fila con nombre vacío para id {cargo_id}, se omite.")
                continue

            cargo = Cargo.query.get(cargo_id)

            if cargo is None:
                cargo = Cargo(id=cargo_id, nombre=nombre)
                db.session.add(cargo)
                count_new += 1
                modo = "CREADO"
            else:
                cargo.nombre = nombre
                count_updated += 1
                modo = "ACTUALIZADO"

            click.echo(f" - {modo}: {cargo_id} → {nombre}")

    db.session.commit()
    click.echo(f"✅ Importación de cargos finalizada. Nuevos: {count_new}, Actualizados: {count_updated}")

@click.command("import-cargos-trabajadores")
@click.argument("csv_path")
@with_appcontext
def import_cargos_trabajadores(csv_path):
    """
    Asigna cargos a los trabajadores según columna 'cargo' del CSV.
    """
    from .models import Trabajador, Cargo

    click.echo(f"📥 Asignando cargos a trabajadores desde: {csv_path}")

    count_ok = 0
    count_not_found = 0
    count_trab_not_found = 0

    # Cargar CSV
    with open(csv_path, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)

        for row in reader:
            rut = (row.get("rut") or "").strip()
            cargo_nombre = (row.get("cargo") or "").strip()

            if not rut:
                continue

            trab = Trabajador.query.filter_by(rut=rut).first()
            if not trab:
                click.echo(f"⚠️ Trabajador con RUT {rut} no existe en la BD.")
                count_trab_not_found += 1
                continue

            if not cargo_nombre:
                click.echo(f"⚠️ Trabajador {rut} no tiene cargo en CSV.")
                continue

            cargo = Cargo.query.filter_by(nombre=cargo_nombre).first()

            if cargo:
                trab.cargo = cargo
                count_ok += 1
            else:
                click.echo(f"❌ Cargo NO encontrado: '{cargo_nombre}' (RUT {rut})")
                count_not_found += 1

    db.session.commit()

    click.echo("🎯 Resultado final:")
    click.echo(f"   ✔️ Cargos asignados: {count_ok}")
    click.echo(f"   ❗ Cargos no encontrados: {count_not_found}")
    click.echo(f"   ❗ Trabajadores no encontrados en BD: {count_trab_not_found}")


def register_cli(app):
    app.cli.add_command(import_trabajadores)
    app.cli.add_command(import_cargos)
    app.cli.add_command(import_cargos_trabajadores)
    # (si luego agregamos import-bancos, lo sumamos aquí también)
