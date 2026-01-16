# web/app/cli.py
from __future__ import annotations

import csv
import re
from datetime import datetime
from typing import Optional, Tuple

import click
from flask.cli import with_appcontext

from .extensions import db
from .models import Trabajador, Banco, Cargo, User, Role, Obra, AFP, Salud, Contrato, Empleador, Horario
from decimal import Decimal, InvalidOperation


# =========================
# Helpers
# =========================

def _parse_date(value: str | None):
    """Convierte un string de fecha a objeto date, o None si viene vacío/ inválido."""
    if not value:
        return None
    value = str(value).strip()
    if not value:
        return None

    for fmt in ("%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y"):
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            continue
    return None


def _to_bool(v: str | None) -> Optional[bool]:
    if v is None:
        return None
    s = str(v).strip().lower()
    if s in ("1", "true", "t", "si", "sí", "y", "yes"):
        return True
    if s in ("0", "false", "f", "no", "n"):
        return False
    return None


def _clean_rut_digits(rut: str) -> str:
    """Deja solo dígitos."""
    return re.sub(r"[^0-9]", "", rut or "")


def _parse_rut_completo(value: str) -> Tuple[str, str]:
    """
    Acepta:
      - 12.345.678-5
      - 12345678-5
      - 123456785
    Retorna: (rut_sin_dv, dv)
    """
    s = (value or "").strip().upper()
    s = s.replace(".", "").replace(" ", "")

    if "-" in s:
        r, d = s.split("-", 1)
        return _clean_rut_digits(r), (d.strip()[:1] if d else "")

    # Si viene sin guion: último carácter es DV
    s2 = re.sub(r"[^0-9K]", "", s)
    if len(s2) >= 2:
        return _clean_rut_digits(s2[:-1]), s2[-1]
    return _clean_rut_digits(s2), ""


def _parse_int_like(value: str | None) -> Optional[int]:
    """
    Parsea enteros tolerando Excel:
    - "37"
    - "037"
    - "37.0"
    - "37,0"
    """
    if value is None:
        return None
    s = str(value).strip()
    if not s:
        return None
    s = s.replace(",", ".")
    if re.fullmatch(r"\d+(\.0+)?", s):
        s = s.split(".", 1)[0]
    try:
        return int(s.lstrip("0") or "0")
    except Exception:
        return None


def _get_optional_int(row: dict, key: str) -> Optional[int]:
    return _parse_int_like(row.get(key))


def _detect_dialect(file_obj) -> csv.Dialect:
    """Detecta delimitador (Excel suele ser ;)"""
    sample = file_obj.read(4096)
    file_obj.seek(0)
    try:
        return csv.Sniffer().sniff(sample, delimiters=";,")
    except Exception:
        dialect = csv.excel
        dialect.delimiter = ";"
        return dialect


def _set_if_empty(trab: Trabajador, attr: str, value: object) -> None:
    """
    Setea solo si el atributo actual está vacío (None/"").
    Evita pisar datos ya corregidos manualmente.
    """
    current = getattr(trab, attr, None)
    if current not in (None, "", " "):
        return

    v = value
    if isinstance(v, str):
        v = v.strip()
        if v == "":
            v = None

    if v not in (None, "", " "):
        setattr(trab, attr, v)

def _parse_decimal(value: str | None):
    """
    Parsea decimales tolerando Excel:
    - "1900000"
    - "1.900.000"
    - "1.900.000,00"
    - "1900000,00"
    Retorna Decimal o None.
    """
    if value is None:
        return None
    s = str(value).strip()
    if not s:
        return None

    # quitar espacios
    s = s.replace(" ", "")

    # si viene con separadores miles estilo CL (.) y decimal (,)
    # estrategia: eliminar miles y normalizar decimal a punto
    # caso 1: tiene "," => asumimos "," decimal
    if "," in s:
        s = s.replace(".", "")
        s = s.replace(",", ".")
    else:
        # si no hay coma, puede venir "1.900.000" (miles) o "1900000.50" (decimal)
        # si tiene más de un punto, asumimos miles y los quitamos
        if s.count(".") > 1:
            s = s.replace(".", "")

    try:
        return Decimal(s)
    except (InvalidOperation, ValueError):
        return None


def _require_fk(model, fk_id: int | None, label: str, row_num: int):
    """
    Valida FK opcional/obligatoria según si viene id.
    Retorna instancia o None.
    """
    if fk_id is None:
        return None
    obj = db.session.get(model, fk_id)
    if not obj:
        raise click.ClickException(f"[fila {row_num}] {label} no existe (id={fk_id}).")
    return obj


# =========================
# CLI: Importar Trabajadores
# =========================

@click.command("import-trabajadores")
@click.argument("csv_path", type=click.Path(exists=True, dir_okay=False))
@click.option("--dry-run", is_flag=True, help="Simula importación sin guardar en BD.")
@click.option("--encoding", default="utf-8-sig", show_default=True, help="Encoding del CSV (Excel suele ser utf-8-sig).")
@with_appcontext
def import_trabajadores(csv_path, dry_run, encoding):
    """
    Importa o actualiza trabajadores desde un archivo CSV.

    Requisitos mínimos por fila:
      - obra_id o obra_codigo (trabajadores.obra_id es NOT NULL)
      - nombres, ap_paterno, ap_materno
      - rut_completo (recomendado) o rut (+ dv)

    Uso:
        flask import-trabajadores /tmp/archivo.csv --dry-run
        flask import-trabajadores /tmp/archivo.csv
    """
    click.echo(f"📥 Importando trabajadores desde: {csv_path}")
    click.echo(f"🧪 Dry-run: {'SI' if dry_run else 'NO'}")

    count_new = 0
    count_updated = 0
    count_skipped = 0
    count_errors = 0

    with open(csv_path, newline="", encoding=encoding) as f:
        dialect = _detect_dialect(f)
        reader = csv.DictReader(f, dialect=dialect)

        if not reader.fieldnames:
            raise click.ClickException("El CSV no tiene encabezados.")

        fieldnames = [h.strip() for h in (reader.fieldnames or [])]

        # Validación mínima rut
        if ("rut_completo" not in fieldnames) and ("rut" not in fieldnames):
            raise click.ClickException("Debes incluir la columna 'rut_completo' o 'rut' (idealmente también 'dv').")

        # Requeridos base
        for col in ("nombres", "ap_paterno", "ap_materno"):
            if col not in fieldnames:
                raise click.ClickException(f"Falta columna requerida: {col}")

        # Obra: se acepta obra_id O obra_codigo
        if "obra_id" not in fieldnames and "obra_codigo" not in fieldnames:
            raise click.ClickException("Falta columna requerida: obra_id u obra_codigo")

        # Iteración por filas
        for row_num, row in enumerate(reader, start=2):  # 1 = encabezado
            trab: Optional[Trabajador] = None
            try:
                # ---------------------------
                # 1) RUT / DV
                # ---------------------------
                rut_raw = (row.get("rut_completo") or "").strip()
                if rut_raw:
                    rut, dv = _parse_rut_completo(rut_raw)
                else:
                    rut = _clean_rut_digits((row.get("rut") or "").strip())
                    dv = (row.get("dv") or "").strip().upper()[:1]

                # ---------------------------
                # 2) Datos básicos
                # ---------------------------
                nombres = (row.get("nombres") or "").strip()
                ap_paterno = (row.get("ap_paterno") or "").strip()
                ap_materno = (row.get("ap_materno") or "").strip()

                if not rut or not nombres or not ap_paterno or not ap_materno:
                    count_skipped += 1
                    click.echo(f"⚠️ [SKIP fila {row_num}] Datos básicos incompletos (rut/nombres/apellidos).")
                    continue

                # ---------------------------
                # 3) Resolver obra (obra_id o obra_codigo)
                # ---------------------------
                obra_id = _get_optional_int(row, "obra_id")
                obra_codigo = (row.get("obra_codigo") or "").strip()

                obra = None
                if obra_id is not None:
                    obra = Obra.query.get(obra_id)
                elif obra_codigo:
                    obra = Obra.query.filter_by(codigo=obra_codigo).first()

                if not obra:
                    count_errors += 1
                    click.echo(
                        f"❌ [ERROR fila {row_num}] Obra no encontrada "
                        f"(obra_id={obra_id}, obra_codigo='{obra_codigo}'). (RUT {rut})"
                    )
                    continue

                # ---------------------------
                # 4) Resolver cargo (opcional)
                # ---------------------------
                cargo = None
                cargo_id = _get_optional_int(row, "cargo_id")
                if cargo_id is not None:
                    cargo = Cargo.query.get(cargo_id)
                    if not cargo:
                        click.echo(f"⚠️ Cargo no existe (cargo_id={cargo_id}). (RUT {rut})")

                # ---------------------------
                # 5) Upsert por RUT
                # ---------------------------
                trab = Trabajador.query.filter_by(rut=rut).first()

                if trab is None:
                    trab = Trabajador(
                        rut=rut,
                        dv=dv or None,
                        nombres=nombres,
                        ap_paterno=ap_paterno,
                        ap_materno=ap_materno,
                        obra_id=obra.id,
                        cargo_id=cargo.id if cargo else None,
                    )
                    db.session.add(trab)
                    count_new += 1
                    modo = "CREADO"
                else:
                    # Básicos: actualiza (para corregir variaciones del CSV)
                    trab.dv = dv or trab.dv
                    trab.nombres = nombres
                    trab.ap_paterno = ap_paterno
                    trab.ap_materno = ap_materno

                    # Obra: asigna siempre (modelo NOT NULL; y suele ser “dato vivo”)
                    trab.obra_id = obra.id

                    # Cargo: solo si viene y existe
                    if cargo:
                        trab.cargo_id = cargo.id

                    count_updated += 1
                    modo = "ACTUALIZADO"

                # ---------------------------
                # 6) Campos opcionales (modo "completar ficha": solo si está vacío)
                # ---------------------------

                # Texto / contacto
                if "direccion" in row:
                    _set_if_empty(trab, "direccion", row.get("direccion"))
                if "comuna" in row:
                    _set_if_empty(trab, "comuna", row.get("comuna"))
                if "telefono" in row:
                    _set_if_empty(trab, "telefono", row.get("telefono"))
                if "telefono_emergencia" in row:
                    _set_if_empty(trab, "telefono_emergencia", row.get("telefono_emergencia"))
                if "correo" in row:
                    _set_if_empty(trab, "correo", row.get("correo"))
                if "nacionalidad" in row:
                    _set_if_empty(trab, "nacionalidad", row.get("nacionalidad"))
                if "sexo" in row:
                    _set_if_empty(trab, "sexo", row.get("sexo"))
                if "estado_civil" in row:
                    _set_if_empty(trab, "estado_civil", row.get("estado_civil"))
                if "tipo_trabajador" in row:
                    _set_if_empty(trab, "tipo_trabajador", row.get("tipo_trabajador"))

                # Fechas
                if "fecha_nacimiento" in row and trab.fecha_nacimiento is None:
                    trab.fecha_nacimiento = _parse_date(row.get("fecha_nacimiento"))
                if "fecha_ingreso_empresa" in row and trab.fecha_ingreso_empresa is None:
                    trab.fecha_ingreso_empresa = _parse_date(row.get("fecha_ingreso_empresa"))
                if "fecha_egreso_empresa" in row and trab.fecha_egreso_empresa is None:
                    trab.fecha_egreso_empresa = _parse_date(row.get("fecha_egreso_empresa"))

                # Estado laboral
                if "estado_trabajador" in row:
                    est = (row.get("estado_trabajador") or "").strip().upper()
                    if est and (trab.estado_trabajador in (None, "", " ")):
                        trab.estado_trabajador = est

                # ---------------------------
                # AFP / Salud (por ID)
                # ---------------------------
                # AFP: acepta columna 'afp_id'
                afp_id = _get_optional_int(row, "afp_id")
                if afp_id is not None:
                    afp = db.session.get(AFP, afp_id)
                    if afp:
                        if getattr(trab, "afp_id", None) in (None, 0):
                            trab.afp_id = afp_id
                    else:
                        click.echo(f"⚠️ AFP no existe (afp_id={afp_id}). (RUT {rut})")

                # Salud: acepta 'salud_id' y alias 'id_salud'
                salud_id = _get_optional_int(row, "salud_id")
                if salud_id is None:
                    salud_id = _get_optional_int(row, "id_salud")

                if salud_id is not None:
                    salud = db.session.get(Salud, salud_id)
                    if salud:
                        if getattr(trab, "salud_id", None) in (None, 0):
                            trab.salud_id = salud_id
                    else:
                        click.echo(f"⚠️ Salud no existe (salud_id={salud_id}). (RUT {rut})")


                # ---------------------------
                # Banco (prioridad: SBIF -> nombre) (solo si banco actual está vacío)
                # ---------------------------
                banco_sbif_raw = (row.get("banco_codigo_sbif") or "").strip()
                banco_nombre = (row.get("banco") or "").strip()

                if trab.banco_id in (None, 0):
                    banco = None
                    if banco_sbif_raw:
                        banco_sbif = _parse_int_like(banco_sbif_raw)
                        if banco_sbif is None:
                            click.echo(f"⚠️ SBIF inválido: '{banco_sbif_raw}' (RUT {rut})")
                        else:
                            banco = Banco.query.filter_by(codigo_sbif=str(banco_sbif)).first()
                            if not banco:
                                # algunos registros podrían tener ceros a la izquierda en BD, probamos fallback
                                banco = Banco.query.filter_by(codigo_sbif=f"{banco_sbif:0d}").first()
                            if not banco:
                                click.echo(f"⚠️ Banco no encontrado por SBIF: {banco_sbif} (RUT {rut})")

                    elif banco_nombre:
                        banco = Banco.query.filter_by(nombre=banco_nombre).first()
                        if not banco:
                            click.echo(f"⚠️ Banco no encontrado por nombre: '{banco_nombre}' (RUT {rut})")

                    if banco:
                        trab.banco = banco

                # Datos de cuenta (solo si vacío)
                if "tipo_cuenta" in row:
                    _set_if_empty(trab, "tipo_cuenta", row.get("tipo_cuenta"))

                if "cuenta_numero" in row:
                    _set_if_empty(trab, "cuenta_numero", row.get("cuenta_numero"))

                if "cuenta_rut" in row:
                    _set_if_empty(trab, "cuenta_rut", row.get("cuenta_rut"))

                # Compatibilidad con CSV antiguo
                if "numero_cta_bancaria" in row and not (row.get("cuenta_numero") or "").strip():
                    _set_if_empty(trab, "cuenta_numero", row.get("numero_cta_bancaria"))

                # Flags booleanos (solo si viene valor válido; y si campo actual está vacío/None)
                for bcol, attr in [
                    ("pago_tercero_activo", "pago_tercero_activo"),
                    ("apv_activo", "apv_activo"),
                    ("cav_activo", "cav_activo"),
                    ("es_extranjero", "es_extranjero"),
                    ("es_discapacitado", "es_discapacitado"),
                    ("es_pensionado", "es_pensionado"),
                    ("tiene_examen_preocupacional", "tiene_examen_preocupacional"),
                    ("tiene_curso_altura", "tiene_curso_altura"),
                    ("tiene_induccion_obra", "tiene_induccion_obra"),
                ]:
                    if bcol in row:
                        b = _to_bool(row.get(bcol))
                        if b is not None:
                            current = getattr(trab, attr, None)
                            if current in (None,):
                                setattr(trab, attr, b)

                # Fechas relacionadas a flags (solo si vacío)
                if "fecha_examen_preocupacional" in row and trab.fecha_examen_preocupacional is None:
                    trab.fecha_examen_preocupacional = _parse_date(row.get("fecha_examen_preocupacional"))
                if "fecha_vencimiento_curso_altura" in row and trab.fecha_vencimiento_curso_altura is None:
                    trab.fecha_vencimiento_curso_altura = _parse_date(row.get("fecha_vencimiento_curso_altura"))
                if "fecha_induccion_obra" in row and trab.fecha_induccion_obra is None:
                    trab.fecha_induccion_obra = _parse_date(row.get("fecha_induccion_obra"))

                click.echo(
                    f" - {modo}: {rut}-{dv or (trab.dv or '')} | {trab.nombres} {trab.ap_paterno} | obra_id={obra.id}"
                )

            except Exception as e:
                db.session.rollback()  # <-- CLAVE: limpia transacción abortada
                count_errors += 1
                rut_dbg = (row.get("rut") or row.get("rut_completo") or "").strip()
                click.echo(f"❌ [ERROR fila {row_num}] {e} (RUT {rut_dbg})")
                continue


    # Commit / rollback
    if dry_run:
        db.session.rollback()
        click.echo("🧪 Dry-run: rollback aplicado (no se guardó nada).")
    else:
        db.session.commit()
        click.echo("💾 Commit aplicado (cambios guardados).")

    click.echo("✅ Importación finalizada.")
    click.echo(f"   Nuevos: {count_new}")
    click.echo(f"   Actualizados: {count_updated}")
    click.echo(f"   Omitidos: {count_skipped}")
    click.echo(f"   Errores: {count_errors}")


# =========================
# CLI: Importar Cargos
# =========================

@click.command("import-cargos")
@click.argument("csv_path", type=click.Path(exists=True, dir_okay=False))
@click.option("--encoding", default="utf-8-sig", show_default=True)
@with_appcontext
def import_cargos(csv_path, encoding):
    """
    Importa o actualiza la tabla de CARGOS desde un CSV con columnas:
    id,nombre
    """
    click.echo(f"🧩 Importando cargos desde: {csv_path}")

    count_new = 0
    count_updated = 0

    with open(csv_path, newline="", encoding=encoding) as f:
        dialect = _detect_dialect(f)
        reader = csv.DictReader(f, dialect=dialect)

        for row in reader:
            try:
                cargo_id = int(str(row.get("id") or "").strip())
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


# =========================
# CLI: Asignar Cargos a Trabajadores por nombre
# =========================

@click.command("import-cargos-trabajadores")
@click.argument("csv_path", type=click.Path(exists=True, dir_okay=False))
@click.option("--encoding", default="utf-8-sig", show_default=True)
@with_appcontext
def import_cargos_trabajadores(csv_path, encoding):
    """
    Asigna cargos a los trabajadores según columna 'cargo' del CSV.
    """
    click.echo(f"📥 Asignando cargos a trabajadores desde: {csv_path}")

    count_ok = 0
    count_not_found = 0
    count_trab_not_found = 0

    with open(csv_path, newline="", encoding=encoding) as f:
        dialect = _detect_dialect(f)
        reader = csv.DictReader(f, dialect=dialect)

        for row in reader:
            rut = _clean_rut_digits((row.get("rut") or "").strip())
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


# =========================
# CLI: Roles / Admin
# =========================

@click.command("seed-roles")
@with_appcontext
def seed_roles():
    for name in ("ADMIN", "OPERADOR", "REVISOR"):
        if not Role.query.filter_by(name=name).first():
            db.session.add(Role(name=name))
    db.session.commit()
    click.echo("Roles sembrados: ADMIN, OPERADOR, REVISOR")


@click.command("create-admin")
@click.option("--username", required=True)
@click.option("--password", required=True)
@with_appcontext
def create_admin(username, password):
    if User.query.filter_by(username=username).first():
        raise click.ClickException("Ya existe un usuario con ese username.")

    admin_role = Role.query.filter_by(name="ADMIN").first()
    if not admin_role:
        raise click.ClickException("No existe el rol ADMIN. Ejecute primero: flask seed-roles")

    u = User(username=username, is_active=True)
    u.set_password(password)
    u.roles.append(admin_role)
    db.session.add(u)
    db.session.commit()
    click.echo(f"ADMIN creado: {username}")


# =========================
# CLI: Importar Contratos
# =========================

@click.command("import-contratos")
@click.argument("csv_path", type=click.Path(exists=True, dir_okay=False))
@click.option("--dry-run", is_flag=True, help="Simula importación sin guardar en BD.")
@click.option("--encoding", default="utf-8-sig", show_default=True, help="Encoding del CSV.")
@click.option(
    "--modo",
    type=click.Choice(["insert", "upsert"], case_sensitive=False),
    default="insert",
    show_default=True,
    help="insert: solo crea; upsert: si existe contrato (por trabajador+empleador+fecha_inicio) actualiza.",
)
@with_appcontext
def import_contratos(csv_path, dry_run, encoding, modo):
    """
    Importa contratos desde CSV usando rut_sin_dv para resolver trabajador_id.

    Encabezados esperados (mínimos recomendados):
      rut_sin_dv, empleador_id, obra_id, cargo_id, tipo_contrato, fecha_inicio, estado_contrato

    Opcionales:
      fecha_termino, jornada, horas_semanales, horario_id,
      sueldo_base, asignacion_movilizacion, asignacion_colacion, asignacion_herramientas,
      causal_termino, fecha_finiquito

    Regla negocio (alineada a tu UI):
      - No permite crear un segundo contrato VIGENTE para el mismo trabajador+empleador.
    """
    click.echo(f"📥 Importando contratos desde: {csv_path}")
    click.echo(f"🧪 Dry-run: {'SI' if dry_run else 'NO'}")
    click.echo(f"⚙️ Modo: {modo.upper()}")

    count_new = 0
    count_updated = 0
    count_skipped = 0
    count_errors = 0

    with open(csv_path, newline="", encoding=encoding) as f:
        dialect = _detect_dialect(f)
        reader = csv.DictReader(f, dialect=dialect)

        if not reader.fieldnames:
            raise click.ClickException("El CSV no tiene encabezados.")

        fieldnames = [h.strip() for h in (reader.fieldnames or [])]

        # Validaciones mínimas
        for col in ("rut_sin_dv", "empleador_id", "obra_id", "cargo_id", "tipo_contrato", "fecha_inicio", "estado_contrato"):
            if col not in fieldnames:
                raise click.ClickException(f"Falta columna requerida: {col}")

        for row_num, row in enumerate(reader, start=2):
            try:
                rut = _clean_rut_digits((row.get("rut_sin_dv") or "").strip())
                if not rut:
                    count_skipped += 1
                    click.echo(f"⚠️ [SKIP fila {row_num}] rut_sin_dv vacío.")
                    continue

                trabajador = Trabajador.query.filter_by(rut=rut).first()
                if not trabajador:
                    count_errors += 1
                    click.echo(f"❌ [ERROR fila {row_num}] Trabajador no existe (rut={rut}).")
                    continue

                empleador_id = _get_optional_int(row, "empleador_id")
                obra_id = _get_optional_int(row, "obra_id")
                cargo_id = _get_optional_int(row, "cargo_id")

                if not empleador_id or not obra_id or not cargo_id:
                    count_errors += 1
                    click.echo(f"❌ [ERROR fila {row_num}] FK obligatoria vacía/ inválida (empleador/obra/cargo). rut={rut}")
                    continue

                empleador = _require_fk(Empleador, empleador_id, "Empleador", row_num)
                obra = _require_fk(Obra, obra_id, "Obra", row_num)
                cargo = _require_fk(Cargo, cargo_id, "Cargo", row_num)

                tipo_contrato = (row.get("tipo_contrato") or "").strip()
                if not tipo_contrato:
                    count_errors += 1
                    click.echo(f"❌ [ERROR fila {row_num}] tipo_contrato vacío. rut={rut}")
                    continue

                fecha_inicio = _parse_date(row.get("fecha_inicio"))
                if not fecha_inicio:
                    count_errors += 1
                    click.echo(f"❌ [ERROR fila {row_num}] fecha_inicio inválida/vacía. rut={rut}")
                    continue

                fecha_termino = _parse_date(row.get("fecha_termino"))

                estado_contrato = (row.get("estado_contrato") or "").strip().upper()
                if not estado_contrato:
                    estado_contrato = "VIGENTE"

                # Horario (opcional)
                horario_id = _get_optional_int(row, "horario_id")
                horario = None
                if horario_id:
                    horario = _require_fk(Horario, horario_id, "Horario", row_num)
                    # Si existe atributo "activo", respetar
                    if hasattr(horario, "activo") and (not horario.activo):
                        count_errors += 1
                        click.echo(f"❌ [ERROR fila {row_num}] horario_id={horario_id} no está activo. rut={rut}")
                        continue

                jornada = (row.get("jornada") or "").strip() or None
                horas_semanales = _get_optional_int(row, "horas_semanales")

                sueldo_base = _parse_decimal(row.get("sueldo_base"))
                asign_mov = _parse_decimal(row.get("asignacion_movilizacion"))
                asign_col = _parse_decimal(row.get("asignacion_colacion"))
                asign_her = _parse_decimal(row.get("asignacion_herramientas"))

                causal_termino = (row.get("causal_termino") or "").strip() or None
                fecha_finiquito = _parse_date(row.get("fecha_finiquito"))

                # -----------------------------------------
                # Regla negocio: un VIGENTE por trabajador+empleador
                # (igual que routes.py)
                # -----------------------------------------
                if estado_contrato == "VIGENTE":
                    existe_vigente = (
                        Contrato.query
                        .filter(
                            Contrato.trabajador_id == trabajador.id,
                            Contrato.empleador_id == empleador_id,
                            Contrato.estado_contrato == "VIGENTE",
                        )
                        .first()
                    )
                    if existe_vigente:
                        # Decisión conservadora: no tocar lo existente, solo reportar.
                        count_skipped += 1
                        click.echo(
                            f"⚠️ [SKIP fila {row_num}] Ya existe contrato VIGENTE "
                            f"(contrato_id={existe_vigente.id}) para trabajador rut={rut} con empleador_id={empleador_id}."
                        )
                        continue

                # -----------------------------------------
                # Identificador "natural" para upsert
                # (trabajador+empleador+fecha_inicio)
                # -----------------------------------------
                contrato_existente = None
                if modo.lower() == "upsert":
                    contrato_existente = (
                        Contrato.query
                        .filter(
                            Contrato.trabajador_id == trabajador.id,
                            Contrato.empleador_id == empleador_id,
                            Contrato.fecha_inicio == fecha_inicio,
                        )
                        .first()
                    )

                if contrato_existente:
                    c = contrato_existente
                    c.obra_id = obra_id
                    c.cargo_id = cargo_id
                    c.tipo_contrato = tipo_contrato
                    c.fecha_termino = fecha_termino
                    c.horario_id = horario_id or None
                    c.jornada = jornada
                    c.horas_semanales = horas_semanales
                    c.sueldo_base = sueldo_base
                    c.asignacion_movilizacion = asign_mov
                    c.asignacion_colacion = asign_col
                    c.asignacion_herramientas = asign_her
                    c.estado_contrato = estado_contrato
                    c.causal_termino = causal_termino
                    c.fecha_finiquito = fecha_finiquito
                    count_updated += 1
                    modo_txt = f"ACTUALIZADO contrato_id={c.id}"
                else:
                    c = Contrato(
                        trabajador_id=trabajador.id,
                        empleador_id=empleador_id,
                        obra_id=obra_id,
                        cargo_id=cargo_id,
                        tipo_contrato=tipo_contrato,
                        fecha_inicio=fecha_inicio,
                        fecha_termino=fecha_termino,
                        horario_id=horario_id or None,
                        jornada=jornada,
                        horas_semanales=horas_semanales,
                        sueldo_base=sueldo_base,
                        asignacion_movilizacion=asign_mov,
                        asignacion_colacion=asign_col,
                        asignacion_herramientas=asign_her,
                        estado_contrato=estado_contrato,
                        causal_termino=causal_termino,
                        fecha_finiquito=fecha_finiquito,
                    )
                    db.session.add(c)
                    count_new += 1
                    modo_txt = "CREADO"

                # Sincronizar ficha si queda vigente (igual a tu UI)
                if estado_contrato == "VIGENTE":
                    if trabajador.obra_id != obra_id:
                        trabajador.obra_id = obra_id
                    if trabajador.cargo_id != cargo_id:
                        trabajador.cargo_id = cargo_id

                click.echo(
                    f" - {modo_txt}: rut={rut} | {trabajador.nombres} {trabajador.ap_paterno} | "
                    f"empleador_id={empleador_id} obra_id={obra_id} cargo_id={cargo_id} inicio={fecha_inicio}"
                )

            except Exception as e:
                db.session.rollback()
                count_errors += 1
                click.echo(f"❌ [ERROR fila {row_num}] {e}")
                continue

    if dry_run:
        db.session.rollback()
        click.echo("🧪 Dry-run: rollback aplicado (no se guardó nada).")
    else:
        db.session.commit()
        click.echo("💾 Commit aplicado (cambios guardados).")

    click.echo("✅ Importación contratos finalizada.")
    click.echo(f"   Nuevos: {count_new}")
    click.echo(f"   Actualizados: {count_updated}")
    click.echo(f"   Omitidos: {count_skipped}")
    click.echo(f"   Errores: {count_errors}")


def register_cli(app):
    app.cli.add_command(import_trabajadores)
    app.cli.add_command(import_cargos)
    app.cli.add_command(import_cargos_trabajadores)
    app.cli.add_command(seed_roles)
    app.cli.add_command(create_admin)
    app.cli.add_command(import_contratos)