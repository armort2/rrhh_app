# web/app/models_legacy.py
from __future__ import annotations
from datetime import date, datetime, timezone

from datetime import date
from flask_login import UserMixin
from sqlalchemy.sql import func
from sqlalchemy import ForeignKey, CheckConstraint, Boolean, DateTime, Column, JSON
from sqlalchemy.orm import relationship, Mapped, mapped_column
from sqlalchemy.dialects.postgresql import JSONB
from werkzeug.security import check_password_hash, generate_password_hash
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy import JSON, text
import sqlalchemy as sa

from .config import (
    NEXTCLOUD_BASE_PATH,
    generar_nombre_documento,
    normalizar_nombre_trabajador,
)
from .extensions import db


# ==========================
# Seguridad / Accesos (RBAC + Obras)
# ==========================

user_roles = db.Table(
    "user_roles",
    db.Column("user_id", db.Integer, db.ForeignKey("users.id"), primary_key=True),
    db.Column("role_id", db.Integer, db.ForeignKey("roles.id"), primary_key=True),
)

user_obras = db.Table(
    "user_obras",
    db.Column("user_id", db.Integer, db.ForeignKey("users.id"), primary_key=True),
    db.Column("obra_id", db.Integer, db.ForeignKey("obras.id"), primary_key=True),
)


class Role(db.Model):
    __tablename__ = "roles"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(30), unique=True, nullable=False)  # ADMIN/OPERADOR/REVISOR

    def __repr__(self):
        return f"<Role {self.name}>"


class User(db.Model, UserMixin):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)

    # Credenciales
    username = db.Column(db.String(80), unique=True, nullable=False, index=True)
    email = db.Column(db.String(120), unique=True, nullable=True, index=True)

    # Datos adicionales (perfil)
    # RUT en formato sugerido: 12345678-9 (sin puntos, con guion)
    rut = db.Column(db.String(12), unique=False, nullable=True, index=True)
    # Nombre visible para listados/reportes (no es username)
    nombre = db.Column(db.String(120), nullable=True, index=True)

    password_hash = db.Column(db.String(255), nullable=False)

    is_active = db.Column(db.Boolean, nullable=False, default=True)
    must_change_password = db.Column(db.Boolean, nullable=False, default=False)

    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    last_login_at = db.Column(db.DateTime, nullable=True)

    roles = db.relationship("Role", secondary=user_roles, lazy="joined")
    obras = db.relationship("Obra", secondary=user_obras, lazy="joined")

    def set_password(self, password: str) -> None:
        self.password_hash = generate_password_hash(password)

    def check_password(self, password: str) -> bool:
        return check_password_hash(self.password_hash, password)

    def has_role(self, *role_names: str) -> bool:
        wanted = {(rn or "").strip().upper() for rn in role_names if (rn or "").strip()}
        user_roles_ = {(r.name or "").strip().upper() for r in self.roles}
        return bool(user_roles_.intersection(wanted))

    def can(self, permission: str) -> bool:
        from .services.access_control import user_can
        return user_can(self, permission)

    def has_any_permission(self, *permissions: str) -> bool:
        from .services.access_control import user_has_any_permission
        return user_has_any_permission(self, *permissions)

    def can_access_obra(self, obra_id: int | None) -> bool:
        """
        Control de acceso por obra.
        - ADMIN: acceso total.
        - Otros: acceso solo si la obra está asignada al usuario.
        """
        if self.has_role("ADMIN"):
            return True
        if obra_id is None:
            return False
        return any(o.id == obra_id for o in self.obras)

    def __repr__(self):
        return f"<User {self.username} active={self.is_active}>"



# ==========================
# Tablas maestras
# ==========================

class Empleador(db.Model):
    """
    Empresa del grupo: Constructora Valencia, Salem, Terratrán, etc.
    """
    __tablename__ = "empleadores"

    id = db.Column(db.Integer, primary_key=True)
    razon_social = db.Column(db.String(200), nullable=False)
    rut = db.Column(db.String(20), nullable=True)
    giro = db.Column(db.String(200), nullable=True)
    direccion = db.Column(db.String(250), nullable=True)
    comuna = db.Column(db.String(100), nullable=True)
    rut_rep_legal = db.Column(db.String(20), nullable=True)
    nombre_rep_legal = db.Column(db.String(150), nullable=True)

    contratos = db.relationship("Contrato", back_populates="empleador", lazy=True)
    obras = db.relationship("Obra", back_populates="empleador", lazy=True)

    # Expediente (eventos)
    eventos = db.relationship("EventoLaboral", back_populates="empleador", lazy=True)

    def __repr__(self):
        return f"<Empleador {self.razon_social}>"


class Mutual(db.Model):
    """
    Mutual de seguridad: ACHS, IST, Mutual, etc.
    Generalmente asociada al empleador u obra.
    """
    __tablename__ = "mutuales"

    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(150), nullable=False)

    empleadores = db.relationship("EmpleadorMutual", back_populates="mutual", lazy=True)

    def __repr__(self):
        return f"<Mutual {self.nombre}>"


class EmpleadorMutual(db.Model):
    """
    Relación Empleador - Mutual (por si una empresa cambia de mutual en el tiempo).
    """
    __tablename__ = "empleador_mutual"

    id = db.Column(db.Integer, primary_key=True)
    empleador_id = db.Column(db.Integer, db.ForeignKey("empleadores.id"), nullable=False)
    mutual_id = db.Column(db.Integer, db.ForeignKey("mutuales.id"), nullable=False)
    vigente = db.Column(db.Boolean, nullable=False, default=True)

    empleador = db.relationship("Empleador", backref="relaciones_mutual")
    mutual = db.relationship("Mutual", back_populates="empleadores")


class AFP(db.Model):
    __tablename__ = "afp"

    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(120), nullable=False, unique=True)

    trabajadores = db.relationship("Trabajador", back_populates="afp", lazy=True)

    def __repr__(self):
        return f"<AFP {self.nombre}>"


class Salud(db.Model):
    """
    Fonasa / Isapres. 'tipo' permite saber si aplica plan UF o no.
    """
    __tablename__ = "salud"

    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(120), nullable=False, unique=True)
    tipo = db.Column(db.String(20), nullable=False)  # "FONASA" o "ISAPRE"

    trabajadores = db.relationship("Trabajador", back_populates="salud", lazy=True)

    def __repr__(self):
        return f"<Salud {self.nombre} ({self.tipo})>"


class Banco(db.Model):
    __tablename__ = "bancos"

    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(120), nullable=False, unique=True)
    codigo_sbif = db.Column(db.String(10), nullable=True)

    trabajadores = db.relationship(
        "Trabajador",
        back_populates="banco",
        lazy=True,
        foreign_keys="Trabajador.banco_id",
    )

    def __repr__(self):
        return f"<Banco {self.nombre}>"


class CajaCompensacion(db.Model):
    __tablename__ = "cajas_compensacion"

    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(150), nullable=False, unique=True)

    trabajadores = db.relationship("Trabajador", back_populates="caja_compensacion", lazy=True)

    def __repr__(self):
        return f"<CajaCompensacion {self.nombre}>"

class Tercero(db.Model):
    """
    Tercero: proveedor (empresa) o persona que presta servicios.
    Base para nóminas bancarias de pagos a terceros.
    """
    __tablename__ = "terceros"

    id = db.Column(db.Integer, primary_key=True)

    # Identificación principal
    rut_num = db.Column(db.Integer, nullable=False, unique=True, index=True)
    dv = db.Column(db.String(2), nullable=False)

    # Nombre / razón social (según origen Excel)
    ap_paterno = db.Column(db.String(200), nullable=False)   # razón social o apellido paterno
    ap_materno = db.Column(db.String(200), nullable=True)
    nombres = db.Column(db.String(200), nullable=True)

    correo = db.Column(db.String(150), nullable=True)

    # Cuenta bancaria (receptor)
    banco_id = db.Column(db.Integer, db.ForeignKey("bancos.id"), nullable=True)
    banco = db.relationship("Banco", foreign_keys=[banco_id])

    cuenta_numero = db.Column(db.String(80), nullable=True)

    # Rut asociado a la cuenta (si aplica / viene en Excel)
    rut_cta_num = db.Column(db.Integer, nullable=True)
    rut_cta_dv = db.Column(db.String(2), nullable=True)

    # Estado corporativo
    estado = db.Column(db.String(20), nullable=False, default="VIGENTE", index=True)

    creado_en = db.Column(db.DateTime(timezone=True), server_default=func.now(), nullable=False)
    actualizado_en = db.Column(db.DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    @property
    def rut_completo(self) -> str:
        r = str(self.rut_num) if self.rut_num is not None else ""
        d = (self.dv or "").strip().upper()
        return f"{r}-{d}" if r and d else r

    @property
    def rut_cta_completo(self) -> str:
        if self.rut_cta_num is None:
            return ""
        r = str(self.rut_cta_num)
        d = (self.rut_cta_dv or "").strip().upper()
        return f"{r}-{d}" if r and d else r

    @property
    def nombre_display(self) -> str:
        """
        - Si es persona: 'AP PATERNO AP MATERNO, NOMBRES'
        - Si es empresa (sin nombres): 'RAZON SOCIAL'
        """
        ap_pat = (self.ap_paterno or "").strip()
        ap_mat = (self.ap_materno or "").strip()
        noms = (self.nombres or "").strip()

        if noms:
            apellidos = " ".join([x for x in [ap_pat, ap_mat] if x])
            if apellidos:
                return f"{apellidos}, {noms}".strip(", ").strip()
            return noms

        # empresa / razón social
        full = " ".join([x for x in [ap_pat, ap_mat] if x]).strip()
        return full or "-"

    def __repr__(self):
        return f"<Tercero {self.rut_completo} {self.nombre_display} estado={self.estado}>"

class Cargo(db.Model):
    __tablename__ = "cargos"

    activo = db.Column(db.Boolean, nullable=False, default=True)

    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(150), nullable=False)
    descripcion = db.Column(db.String(300), nullable=True)
    categoria = db.Column(db.String(100), nullable=True)

    contratos = db.relationship("Contrato", back_populates="cargo", lazy=True)
    trabajadores = db.relationship("Trabajador", back_populates="cargo", lazy=True)

    def __repr__(self):
        return f"<Cargo {self.nombre}>"


# ==========================
# Causales de término (catálogo)
# ==========================

class CausalTermino(db.Model):
    __tablename__ = "causales_termino"

    id = db.Column(db.Integer, primary_key=True)

    causal_finiquito = db.Column(db.Text, nullable=False)
    causal_resumida = db.Column(db.String(120), nullable=False)

    activo = db.Column(db.Boolean, nullable=False, default=True)

    created_at = db.Column(db.DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = db.Column(db.DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    desvinculaciones = db.relationship("Desvinculacion", back_populates="causal", lazy=True)

    requiere_carta = db.Column(db.Boolean, nullable=False, default=True)
    carta_template = db.Column(db.String(120), nullable=True)

    def __repr__(self):
        return f"<CausalTermino {self.id} {self.causal_resumida}>"
    

# ==========================
# Horarios (catálogo)
# ==========================

class Horario(db.Model):
    __tablename__ = "horarios"

    id = db.Column(db.Integer, primary_key=True)

    nombre = db.Column(db.String(80), nullable=False, unique=True)
    descripcion = db.Column(db.Text, nullable=True)  # texto contractual “bonito”
    activo = db.Column(db.Boolean, nullable=False, default=True)

    creado_en = db.Column(db.DateTime(timezone=True), server_default=func.now())
    actualizado_en = db.Column(db.DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    tramos = db.relationship(
        "HorarioTramo",
        back_populates="horario",
        lazy=True,
        cascade="all, delete-orphan",
        order_by="HorarioTramo.dia_semana, HorarioTramo.orden",
    )

    # ✅ Relación bidireccional (consistente con Contrato.horario)
    contratos = db.relationship(
        "Contrato",
        back_populates="horario",
        lazy=True,
    )

    def __repr__(self):
        return f"<Horario {self.nombre} activo={self.activo}>"


class HorarioTramo(db.Model):
    __tablename__ = "horario_tramos"

    id = db.Column(db.Integer, primary_key=True)

    horario_id = db.Column(db.Integer, db.ForeignKey("horarios.id"), nullable=False, index=True)
    horario = db.relationship("Horario", back_populates="tramos")

    dia_semana = db.Column(db.Integer, nullable=False)  # 0=Lun ... 6=Dom
    hora_inicio = db.Column(db.Time, nullable=False)
    hora_termino = db.Column(db.Time, nullable=False)

    orden = db.Column(db.Integer, nullable=False, default=1)

    __table_args__ = (
        db.CheckConstraint("dia_semana >= 0 AND dia_semana <= 6", name="ck_horario_tramo_dia"),
    )

    def __repr__(self):
        return f"<HorarioTramo horario={self.horario_id} dia={self.dia_semana} {self.hora_inicio}-{self.hora_termino}>"


# ==========================
# Obras
# ==========================

class Obra(db.Model):
    __tablename__ = "obras"

    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(120), nullable=False)
    codigo = db.Column(db.String(50), nullable=False, unique=True)
    centro_costo = db.Column(db.String(100), nullable=True)
    comuna = db.Column(db.String(100), nullable=True)
    direccion = db.Column(db.String(300), nullable=True)

    empleador_id = db.Column(db.Integer, db.ForeignKey("empleadores.id"), nullable=True)
    empleador = db.relationship("Empleador", back_populates="obras")

    estado = db.Column(db.String(20), nullable=False, default="ACTIVA")  # ACTIVA / CERRADA
    fecha_inicio = db.Column(db.Date, nullable=True)
    fecha_cierre = db.Column(db.Date, nullable=True)

    trabajadores = db.relationship("Trabajador", back_populates="obra", lazy=True)
    contratos = db.relationship("Contrato", back_populates="obra", lazy=True)

    # Expediente (eventos)
    eventos = db.relationship("EventoLaboral", back_populates="obra", lazy=True)

    # Historial (opcional)
    trabajador_historial = db.relationship("TrabajadorObra", back_populates="obra", lazy=True)

    # Datos administrativo para cartas de aviso
    obra_administrativo_nombre = db.Column(db.String(120))
    obra_administrativo_rut = db.Column(db.String(20))
    obra_administrativo_telefono = db.Column(db.String(30))
    obra_administrativo_correo = db.Column(db.String(120))
    obra_administrativo_cargo = db.Column(db.String(120))

    def __repr__(self):
        return f"<Obra {self.codigo} - {self.nombre}>"


# ==========================
# Historial de Obras del Trabajador (preparado, no obligatorio usar hoy)
# ==========================

class TrabajadorObra(db.Model):
    """
    Registro histórico de paso del trabajador por obras.
    Útil para control de acceso fino y trazabilidad.
    """
    __tablename__ = "trabajador_obras"

    id = db.Column(db.Integer, primary_key=True)

    trabajador_id = db.Column(db.Integer, db.ForeignKey("trabajadores.id"), nullable=False, index=True)
    obra_id = db.Column(db.Integer, db.ForeignKey("obras.id"), nullable=False, index=True)

    fecha_inicio = db.Column(db.Date, nullable=False, default=date.today)
    fecha_termino = db.Column(db.Date, nullable=True)

    vigente = db.Column(db.Boolean, nullable=False, default=True)

    creado_en = db.Column(db.DateTime(timezone=True), server_default=func.now())

    trabajador = db.relationship("Trabajador", back_populates="historial_obras")
    obra = db.relationship("Obra", back_populates="trabajador_historial")

    def __repr__(self):
        return f"<TrabajadorObra trab={self.trabajador_id} obra={self.obra_id} vigente={self.vigente}>"


# ==========================
# Trabajador
# ==========================

class Trabajador(db.Model):
    __tablename__ = "trabajadores"

    id = db.Column(db.Integer, primary_key=True)

    # Identificación
    rut = db.Column(db.String(20), unique=True, nullable=False)
    dv = db.Column(db.String(2), nullable=True)
    nombres = db.Column(db.String(100), nullable=False)
    ap_paterno = db.Column(db.String(100), nullable=False)
    ap_materno = db.Column(db.String(100), nullable=True)

    @property
    def rut_completo(self) -> str:
        r = (self.rut or "").strip()
        d = (self.dv or "").strip().upper()
        return f"{r}-{d}" if r and d else r

    # Datos personales
    fecha_nacimiento = db.Column(db.Date, nullable=True)
    nacionalidad = db.Column(db.String(60), nullable=True)
    sexo = db.Column(db.String(10), nullable=True)
    estado_civil = db.Column(db.String(30), nullable=True)

    # Contacto
    direccion = db.Column(db.String(250), nullable=True)
    comuna = db.Column(db.String(100), nullable=True)
    telefono = db.Column(db.String(30), nullable=True)
    telefono_emergencia = db.Column(db.String(30), nullable=True)
    correo = db.Column(db.String(150), nullable=True)

    # Banco del trabajador (cuenta propia)
    banco_id = db.Column(db.Integer, db.ForeignKey("bancos.id"), nullable=True)
    banco = db.relationship(
        "Banco",
        back_populates="trabajadores",
        foreign_keys=[banco_id],
    )

    tipo_cuenta = db.Column(db.String(20), nullable=True)
    cuenta_rut = db.Column(db.String(20), nullable=True)
    cuenta_numero = db.Column(db.String(50), nullable=True)

    # Pago a cuenta de tercero
    pago_tercero_activo = db.Column(db.Boolean, nullable=False, default=False)
    pago_tercero_rut = db.Column(db.String(20), nullable=True)
    pago_tercero_nombre = db.Column(db.String(200), nullable=True)
    pago_tercero_banco_id = db.Column(db.Integer, db.ForeignKey("bancos.id"), nullable=True)
    pago_tercero_banco = db.relationship(
        "Banco",
        foreign_keys=[pago_tercero_banco_id],
    )
    pago_tercero_tipo_cuenta = db.Column(db.String(20), nullable=True)
    pago_tercero_cuenta_numero = db.Column(db.String(50), nullable=True)

    # Previsional base
    afp_id = db.Column(db.Integer, db.ForeignKey("afp.id"), nullable=True)
    afp = db.relationship("AFP", back_populates="trabajadores")

    salud_id = db.Column(db.Integer, db.ForeignKey("salud.id"), nullable=True)
    salud = db.relationship("Salud", back_populates="trabajadores")

    uf_plan_salud = db.Column(db.Numeric(6, 2), nullable=True)

    # Caja de compensación
    caja_compensacion_id = db.Column(db.Integer, db.ForeignKey("cajas_compensacion.id"), nullable=True)
    caja_compensacion = db.relationship("CajaCompensacion", back_populates="trabajadores")

    # APV
    apv_activo = db.Column(db.Boolean, nullable=False, default=False)
    apv_modalidad = db.Column(db.String(20), nullable=True)
    apv_valor = db.Column(db.Numeric(8, 2), nullable=True)
    apv_institucion = db.Column(db.String(120), nullable=True)

    # CAV
    cav_activo = db.Column(db.Boolean, nullable=False, default=False)
    cav_modalidad = db.Column(db.String(20), nullable=True)
    cav_valor = db.Column(db.Numeric(8, 2), nullable=True)
    cav_institucion = db.Column(db.String(120), nullable=True)

    # Cargas, condición especial
    num_cargas_familiares = db.Column(db.Integer, nullable=True)
    es_extranjero = db.Column(db.Boolean, nullable=False, default=False)
    es_discapacitado = db.Column(db.Boolean, nullable=False, default=False)
    es_pensionado = db.Column(db.Boolean, nullable=False, default=False)

    # Seguridad y salud ocupacional
    tiene_examen_preocupacional = db.Column(db.Boolean, nullable=False, default=False)
    fecha_examen_preocupacional = db.Column(db.Date, nullable=True)
    tiene_curso_altura = db.Column(db.Boolean, nullable=False, default=False)
    fecha_vencimiento_curso_altura = db.Column(db.Date, nullable=True)
    tiene_induccion_obra = db.Column(db.Boolean, nullable=False, default=False)
    fecha_induccion_obra = db.Column(db.Date, nullable=True)

    # Relación principal con obra actual
    obra_id = db.Column(db.Integer, db.ForeignKey("obras.id"), nullable=False)
    obra = db.relationship("Obra", back_populates="trabajadores")

    # Cargo actual
    cargo_id = db.Column(db.Integer, db.ForeignKey("cargos.id"), nullable=True)
    cargo = db.relationship("Cargo", back_populates="trabajadores")

    # Estado laboral general
    estado_trabajador = db.Column(db.String(20), nullable=False, default="VIGENTE")
    tipo_trabajador = db.Column(db.String(30), nullable=True)

    fecha_ingreso_empresa = db.Column(db.Date, nullable=True)
    fecha_egreso_empresa = db.Column(db.Date, nullable=True)

    # Auditoría básica
    creado_en = db.Column(db.DateTime(timezone=True), server_default=func.now())
    actualizado_en = db.Column(db.DateTime(timezone=True), onupdate=func.now())

    # Relación con contratos
    contratos = db.relationship("Contrato", back_populates="trabajador", lazy=True)

    # Expediente (eventos)
    eventos = db.relationship(
        "EventoLaboral",
        back_populates="trabajador",
        lazy=True,
        cascade="all, delete-orphan",
    )

    # Historial (opcional)
    historial_obras = db.relationship(
        "TrabajadorObra",
        back_populates="trabajador",
        lazy=True,
        cascade="all, delete-orphan",
    )

    # ==========================
    # Helpers de documentación / Nextcloud
    # ==========================

    @property
    def carpeta_nombre(self) -> str:
        return normalizar_nombre_trabajador(
            self.rut,
            self.nombres,
            self.ap_paterno,
            self.ap_materno,
        )

    @property
    def empleador_preferente(self):
        if not self.contratos:
            return None

        contratos_vigentes = [
            c for c in self.contratos
            if c.estado_contrato == "VIGENTE" and c.empleador is not None
        ]

        if contratos_vigentes:
            contratos_ordenados = sorted(
                contratos_vigentes,
                key=lambda c: (c.fecha_inicio or date.min),
                reverse=True,
            )
            return contratos_ordenados[0].empleador

        contratos_con_empleador = [c for c in self.contratos if c.empleador is not None]
        if contratos_con_empleador:
            contratos_ordenados = sorted(
                contratos_con_empleador,
                key=lambda c: (c.fecha_inicio or date.min),
                reverse=True,
            )
            return contratos_ordenados[0].empleador

        return None

    def ruta_nextcloud(self, empleador_nombre: str) -> str:
        return NEXTCLOUD_BASE_PATH.format(
            empleador=empleador_nombre,
            carpeta_trabajador=self.carpeta_nombre,
        )

    @property
    def ruta_nextcloud_preferente(self) -> str | None:
        emp = self.empleador_preferente
        if not emp:
            return None
        return self.ruta_nextcloud(emp.razon_social)

    def __repr__(self):
        return f"<Trabajador {self.rut} - {self.nombres} {self.ap_paterno}>"

# ==========================
# Desvinculaciones (carta aviso + finiquito)
# ==========================

class Desvinculacion(db.Model):
    __tablename__ = "desvinculaciones"

    id = db.Column(db.Integer, primary_key=True)

    trabajador_id = db.Column(db.Integer, db.ForeignKey("trabajadores.id"), nullable=False, index=True)
    contrato_id = db.Column(db.Integer, db.ForeignKey("contratos.id"), nullable=False, index=True)

    empleador_id = db.Column(db.Integer, db.ForeignKey("empleadores.id"), nullable=True, index=True)
    obra_id = db.Column(db.Integer, db.ForeignKey("obras.id"), nullable=True, index=True)

    causal_id = db.Column(db.Integer, db.ForeignKey("causales_termino.id"), nullable=False, index=True)

    fecha_aviso = db.Column(db.Date, nullable=True)
    fecha_termino = db.Column(db.Date, nullable=False)

    motivo_detalle = db.Column(db.Text, nullable=True)

    estado = db.Column(db.String(20), nullable=False, default="BORRADOR")  # BORRADOR / EMITIDA / ANULADA

    # Rutas/documentos (cuando implementemos generación)
    carta_nombre = db.Column(db.String(255), nullable=True)
    carta_ruta = db.Column(db.Text, nullable=True)
    finiquito_nombre = db.Column(db.String(255), nullable=True)
    finiquito_ruta = db.Column(db.Text, nullable=True)

    meta = db.Column(JSON().with_variant(JSONB, "postgresql"), nullable=True)

    creado_en = db.Column(db.DateTime(timezone=True), server_default=func.now())
    actualizado_en = db.Column(
        db.DateTime(timezone=True),
        server_default=db.func.now(),
        onupdate=db.func.now(),
        nullable=False,
    )

    # Relaciones
    trabajador = db.relationship("Trabajador", backref=db.backref("desvinculaciones", lazy=True))
    contrato = db.relationship("Contrato", backref=db.backref("desvinculaciones", lazy=True))
    empleador = db.relationship("Empleador")
    obra = db.relationship("Obra")

    causal = db.relationship("CausalTermino", back_populates="desvinculaciones")

    def __repr__(self):
        return f"<Desvinculacion {self.id} trab={self.trabajador_id} contrato={self.contrato_id} estado={self.estado}>"


# ==========================
# Contratos
# ==========================

class Contrato(db.Model):
    __tablename__ = "contratos"

    id = db.Column(db.Integer, primary_key=True)

    trabajador_id = db.Column(db.Integer, db.ForeignKey("trabajadores.id"), nullable=False)
    trabajador = db.relationship("Trabajador", back_populates="contratos")

    empleador_id = db.Column(db.Integer, db.ForeignKey("empleadores.id"), nullable=True)
    empleador = db.relationship("Empleador", back_populates="contratos")

    obra_id = db.Column(db.Integer, db.ForeignKey("obras.id"), nullable=True)
    obra = db.relationship("Obra", back_populates="contratos")

    cargo_id = db.Column(db.Integer, db.ForeignKey("cargos.id"), nullable=True)
    cargo = db.relationship("Cargo", back_populates="contratos")

    tipo_contrato = db.Column(db.String(30), nullable=True)
    fecha_inicio = db.Column(db.Date, nullable=True)
    fecha_termino = db.Column(db.Date, nullable=True)

    # NUEVO: horario del catálogo
    horario_id = db.Column(db.Integer, db.ForeignKey("horarios.id"), nullable=True, index=True)
    horario = db.relationship("Horario", back_populates="contratos", lazy="joined")

    # IMPORTANTE: jornada pasa a Text (parche inmediato + compatibilidad)
    jornada = db.Column(db.Text, nullable=True)

    horas_semanales = db.Column(db.Integer, nullable=True)

    sueldo_base = db.Column(db.Numeric(10, 2), nullable=True)
    asignacion_movilizacion = db.Column(db.Numeric(10, 2), nullable=True)
    asignacion_colacion = db.Column(db.Numeric(10, 2), nullable=True)
    asignacion_herramientas = db.Column(db.Numeric(10, 2), nullable=True)

    estado_contrato = db.Column(db.String(20), nullable=False, default="VIGENTE")
    causal_termino = db.Column(db.String(250), nullable=True)
    fecha_finiquito = db.Column(db.Date, nullable=True)

    creado_en = db.Column(db.DateTime(timezone=True), server_default=func.now())
    actualizado_en = db.Column(db.DateTime(timezone=True), onupdate=func.now())

    documentos = db.relationship(
        "DocumentoLaboral",
        back_populates="contrato",
        lazy=True,
        cascade="all, delete-orphan",
    )

    eventos = db.relationship("EventoLaboral", back_populates="contrato", lazy=True)

    def __repr__(self):
        return f"<Contrato {self.id} Trabajador={self.trabajador_id}>"



# ==========================
# Documentos laborales (legado / por contrato)
# ==========================

class DocumentoLaboral(db.Model):
    __tablename__ = "documentos_laborales"

    id = db.Column(db.Integer, primary_key=True)

    contrato_id = db.Column(db.Integer, db.ForeignKey("contratos.id"), nullable=False)
    contrato = db.relationship("Contrato", back_populates="documentos")

    tipo = db.Column(db.String(50), nullable=False)

    nombre_archivo = db.Column(db.String(255), nullable=False)
    ruta_archivo = db.Column(db.String(500), nullable=True)

    estado = db.Column(db.String(20), nullable=False, default="VIGENTE")
    fecha_creacion = db.Column(db.DateTime(timezone=True), server_default=func.now())

    @classmethod
    def crear_para_contrato(
        cls,
        contrato,
        tipo: str,
        fecha_ref: date | None = None,
        extension: str = "pdf",
        ruta_archivo: str | None = None,
        estado: str = "VIGENTE",
    ):
        if not contrato or not contrato.trabajador:
            raise ValueError("Se requiere un contrato con trabajador asociado.")

        trabajador = contrato.trabajador
        ap_paterno = trabajador.ap_paterno or ""

        if fecha_ref is None:
            fecha_ref = contrato.fecha_inicio

        nombre_archivo = generar_nombre_documento(
            tipo=tipo,
            ap_paterno=ap_paterno,
            fecha_ref=fecha_ref,
            extension=extension,
        )

        return cls(
            contrato_id=contrato.id,
            tipo=tipo,
            nombre_archivo=nombre_archivo,
            ruta_archivo=ruta_archivo,
            estado=estado,
        )

    @property
    def carpeta_destino(self) -> str | None:
        if not self.contrato or not self.contrato.trabajador or not self.contrato.empleador:
            return None

        base = self.contrato.trabajador.ruta_nextcloud(self.contrato.empleador.razon_social)
        return f"{base}/{self.tipo.upper()}"

    @property
    def ruta_completa(self) -> str | None:
        carpeta = self.carpeta_destino
        if not carpeta:
            return None
        return f"{carpeta}/{self.nombre_archivo}"

    def __repr__(self):
        return f"<DocumentoLaboral {self.id} Contrato={self.contrato_id} Tipo={self.tipo}>"


# ==========================
# Expediente Laboral (genérico / recomendado)
# ==========================

class EventoLaboral(db.Model):
    """
    Evento/documento en la vida laboral del trabajador.
    Base para anexos, acuerdos de pago, préstamos, amonestaciones, cartas, finiquitos, etc.
    """
    __tablename__ = "eventos_laborales"

    id = db.Column(db.Integer, primary_key=True)

    trabajador_id = db.Column(db.Integer, db.ForeignKey("trabajadores.id"), nullable=False, index=True)
    trabajador = db.relationship("Trabajador", back_populates="eventos")

    contrato_id = db.Column(db.Integer, db.ForeignKey("contratos.id"), nullable=True, index=True)
    contrato = db.relationship("Contrato", back_populates="eventos")

    obra_id = db.Column(db.Integer, db.ForeignKey("obras.id"), nullable=True, index=True)
    obra = db.relationship("Obra", back_populates="eventos")

    empleador_id = db.Column(db.Integer, db.ForeignKey("empleadores.id"), nullable=True, index=True)
    empleador = db.relationship("Empleador", back_populates="eventos")

    categoria = db.Column(db.String(30), nullable=False, default="OTRO")
    tipo = db.Column(db.String(60), nullable=False, default="OTRO")

    titulo = db.Column(db.String(200), nullable=False)

    fecha_evento = db.Column(db.Date, nullable=False, default=date.today)
    estado = db.Column(db.String(20), nullable=False, default="VIGENTE")  # VIGENTE / ANULADO / REEMPLAZADO

    # Archivo / Nextcloud
    nombre_archivo = db.Column(db.String(255), nullable=True)
    ruta_archivo = db.Column(db.String(500), nullable=True)

    # Campos variables, según tipo (Postgres: JSONB)
    meta = db.Column("metadata", db.JSON, nullable=True)

    creado_en = db.Column(db.DateTime(timezone=True), server_default=func.now())
    actualizado_en = db.Column(db.DateTime(timezone=True), onupdate=func.now())

    def __repr__(self):
        return f"<EventoLaboral {self.id} Trabajador={self.trabajador_id} {self.categoria}/{self.tipo} {self.fecha_evento}>"

# ==========================
# Anexo extensión contrato
# ==========================

class AnexoExtensionContrato(db.Model):
    __tablename__ = "anexos_extension_contrato"

    id = db.Column(db.Integer, primary_key=True)

    contrato_id = db.Column(db.Integer, db.ForeignKey("contratos.id"), nullable=False, index=True)
    trabajador_id = db.Column(db.Integer, db.ForeignKey("trabajadores.id"), nullable=False, index=True)
    empleador_id = db.Column(db.Integer, db.ForeignKey("empleadores.id"), nullable=True, index=True)
    obra_id = db.Column(db.Integer, db.ForeignKey("obras.id"), nullable=True, index=True)

    fecha_anexo = db.Column(db.Date, nullable=False, default=date.today)
    fecha_termino_anterior = db.Column(db.Date, nullable=True)
    fecha_termino_nueva = db.Column(db.Date, nullable=False)

    observaciones = db.Column(db.Text, nullable=True)

    # DOCX / PDF / AMBOS
    formato = db.Column(db.String(10), nullable=False, default="AMBOS")

    estado = db.Column(db.String(20), nullable=False, default="VIGENTE")  # VIGENTE/ANULADO/REEMPLAZADO

    docx_nombre = db.Column(db.String(255), nullable=True)
    docx_ruta = db.Column(db.Text, nullable=True)
    pdf_nombre = db.Column(db.String(255), nullable=True)
    pdf_ruta = db.Column(db.Text, nullable=True)

    meta = db.Column(JSON().with_variant(JSONB, "postgresql"), nullable=True)

    creado_en = db.Column(db.DateTime(timezone=True), server_default=func.now())

    # Relaciones (consistentes)
    contrato = db.relationship("Contrato", backref=db.backref("anexos_extension", lazy="dynamic"))
    trabajador = db.relationship("Trabajador")
    empleador = db.relationship("Empleador")
    obra = db.relationship("Obra")

    def __repr__(self):
        return f"<AnexoExtensionContrato {self.id} contrato={self.contrato_id} {self.fecha_termino_anterior}->{self.fecha_termino_nueva}>"

# ==========================
# Anexo contrato indefinido
# ==========================

class AnexoIndefinidoContrato(db.Model):
    __tablename__ = "anexos_indefinido_contrato"

    id = db.Column(db.Integer, primary_key=True)

    contrato_id = db.Column(db.Integer, db.ForeignKey("contratos.id"), nullable=False, index=True)
    trabajador_id = db.Column(db.Integer, db.ForeignKey("trabajadores.id"), nullable=False, index=True)
    empleador_id = db.Column(db.Integer, db.ForeignKey("empleadores.id"), nullable=True, index=True)
    obra_id = db.Column(db.Integer, db.ForeignKey("obras.id"), nullable=True, index=True)

    # Fecha del documento (firma/emisión)
    fecha_anexo = db.Column(db.Date, nullable=False, default=date.today)

    # Desde cuándo pasa a indefinido (lo típico: día siguiente al término anterior)
    fecha_indefinido_desde = db.Column(db.Date, nullable=False)

    # Para trazabilidad: término anterior referencial (contrato o anexo extensión)
    fecha_termino_referencial = db.Column(db.Date, nullable=True)

    observaciones = db.Column(db.Text, nullable=True)

    # DOCX / PDF / AMBOS
    formato = db.Column(db.String(10), nullable=False, default="AMBOS")

    estado = db.Column(db.String(20), nullable=False, default="VIGENTE")  # VIGENTE/ANULADO/REEMPLAZADO

    docx_nombre = db.Column(db.String(255), nullable=True)
    docx_ruta = db.Column(db.Text, nullable=True)
    pdf_nombre = db.Column(db.String(255), nullable=True)
    pdf_ruta = db.Column(db.Text, nullable=True)

    meta = db.Column(JSON().with_variant(JSONB, "postgresql"), nullable=True)

    creado_en = db.Column(db.DateTime(timezone=True), server_default=func.now())

    # Relaciones
    contrato = db.relationship("Contrato", backref=db.backref("anexos_indefinido", lazy="dynamic"))
    trabajador = db.relationship("Trabajador")
    empleador = db.relationship("Empleador")
    obra = db.relationship("Obra")

    def __repr__(self):
        return (
            f"<AnexoIndefinidoContrato {self.id} contrato={self.contrato_id} "
            f"desde={self.fecha_indefinido_desde} estado={self.estado}>"
        )

# ==========================
# Anexo cambio de sueldo
# ==========================
class AnexoCambioSueldoContrato(db.Model):
    __tablename__ = "anexos_cambio_sueldo_contrato"

    id = db.Column(db.Integer, primary_key=True)

    contrato_id = db.Column(db.Integer, db.ForeignKey("contratos.id"), nullable=False, index=True)
    trabajador_id = db.Column(db.Integer, db.ForeignKey("trabajadores.id"), nullable=False, index=True)
    empleador_id = db.Column(db.Integer, db.ForeignKey("empleadores.id"), nullable=True, index=True)
    obra_id = db.Column(db.Integer, db.ForeignKey("obras.id"), nullable=True, index=True)

    # Fecha desde la cual rige el cambio de remuneraciones
    fecha_cambio = db.Column(db.Date, nullable=False, default=date.today)

    # Trazabilidad: montos anteriores y nuevos
    sueldo_base_anterior = db.Column(db.Numeric(10, 2), nullable=True)
    sueldo_base_nuevo = db.Column(db.Numeric(10, 2), nullable=False)

    asignacion_colacion_anterior = db.Column(db.Numeric(10, 2), nullable=True)
    asignacion_colacion_nueva = db.Column(db.Numeric(10, 2), nullable=False, default=0)

    asignacion_movilizacion_anterior = db.Column(db.Numeric(10, 2), nullable=True)
    asignacion_movilizacion_nueva = db.Column(db.Numeric(10, 2), nullable=False, default=0)

    observaciones = db.Column(db.Text, nullable=True)

    # DOCX / PDF / AMBOS
    formato = db.Column(db.String(10), nullable=False, default="AMBOS")
    estado = db.Column(db.String(20), nullable=False, default="VIGENTE")  # VIGENTE/ANULADO/REEMPLAZADO

    docx_nombre = db.Column(db.String(255), nullable=True)
    docx_ruta = db.Column(db.Text, nullable=True)
    pdf_nombre = db.Column(db.String(255), nullable=True)
    pdf_ruta = db.Column(db.Text, nullable=True)

    meta = db.Column(JSON().with_variant(JSONB, "postgresql"), nullable=True)

    creado_en = db.Column(db.DateTime(timezone=True), server_default=func.now())

    contrato = db.relationship("Contrato", backref=db.backref("anexos_cambio_sueldo", lazy="dynamic"))
    trabajador = db.relationship("Trabajador")
    empleador = db.relationship("Empleador")
    obra = db.relationship("Obra")

    def __repr__(self):
        return (
            f"<AnexoCambioSueldoContrato {self.id} contrato={self.contrato_id} "
            f"fecha={self.fecha_cambio} sueldo={self.sueldo_base_anterior}->{self.sueldo_base_nuevo}>"
        )


# ==========================
# Anexo cambio de cargo
# ==========================
class AnexoCambioCargoContrato(db.Model):
    __tablename__ = "anexos_cambio_cargo_contrato"

    id = db.Column(db.Integer, primary_key=True)

    contrato_id = db.Column(db.Integer, db.ForeignKey("contratos.id"), nullable=False, index=True)
    trabajador_id = db.Column(db.Integer, db.ForeignKey("trabajadores.id"), nullable=False, index=True)
    empleador_id = db.Column(db.Integer, db.ForeignKey("empleadores.id"), nullable=True, index=True)
    obra_id = db.Column(db.Integer, db.ForeignKey("obras.id"), nullable=True, index=True)

    # Fecha desde la cual rige el cambio de cargo
    fecha_cambio = db.Column(db.Date, nullable=False, default=date.today)

    # Trazabilidad: cargo anterior y nuevo
    cargo_anterior_id = db.Column(db.Integer, db.ForeignKey("cargos.id"), nullable=True, index=True)
    cargo_anterior_nombre = db.Column(db.String(150), nullable=True)

    cargo_nuevo_id = db.Column(db.Integer, db.ForeignKey("cargos.id"), nullable=False, index=True)
    cargo_nuevo_nombre = db.Column(db.String(150), nullable=False)

    observaciones = db.Column(db.Text, nullable=True)

    # DOCX / PDF / AMBOS
    formato = db.Column(db.String(10), nullable=False, default="AMBOS")
    estado = db.Column(db.String(20), nullable=False, default="VIGENTE")  # VIGENTE/ANULADO/REEMPLAZADO

    docx_nombre = db.Column(db.String(255), nullable=True)
    docx_ruta = db.Column(db.Text, nullable=True)
    pdf_nombre = db.Column(db.String(255), nullable=True)
    pdf_ruta = db.Column(db.Text, nullable=True)

    meta = db.Column(JSON().with_variant(JSONB, "postgresql"), nullable=True)

    creado_en = db.Column(db.DateTime(timezone=True), server_default=func.now())

    contrato = db.relationship("Contrato", backref=db.backref("anexos_cambio_cargo", lazy="dynamic"))
    trabajador = db.relationship("Trabajador")
    empleador = db.relationship("Empleador")
    obra = db.relationship("Obra")
    cargo_anterior = db.relationship("Cargo", foreign_keys=[cargo_anterior_id])
    cargo_nuevo = db.relationship("Cargo", foreign_keys=[cargo_nuevo_id])

    def __repr__(self):
        return (
            f"<AnexoCambioCargoContrato {self.id} contrato={self.contrato_id} "
            f"fecha={self.fecha_cambio} cargo={self.cargo_anterior_nombre}->{self.cargo_nuevo_nombre}>"
        )

# ==========================
# Módulo para controlar Asistencia
# ==========================

class Inasistencia(db.Model):
    __tablename__ = "inasistencias"

    id: Mapped[int] = mapped_column(primary_key=True)

    trabajador_id: Mapped[int] = mapped_column(ForeignKey("trabajadores.id"), index=True, nullable=False)
    contrato_id: Mapped[int | None] = mapped_column(ForeignKey("contratos.id"), index=True, nullable=True)

    fecha: Mapped[date] = mapped_column(index=True, nullable=False)

    # "DIA" o "HORAS"
    tipo: Mapped[str] = mapped_column(db.String(10), nullable=False, default="DIA")

    # Para tipo HORAS, guardamos minutos (ej: 1h30m => 90). Para DIA puede ser NULL.
    minutos_ausentes: Mapped[int | None] = mapped_column(nullable=True)

    motivo: Mapped[str] = mapped_column(db.String(80), nullable=False)
    observacion: Mapped[str | None] = mapped_column(db.String(255), nullable=True)

    creado_por_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    creado_en: Mapped[datetime] = mapped_column(nullable=False, default=datetime.utcnow)

    actualizado_en: Mapped[datetime] = mapped_column(nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    trabajador = relationship("Trabajador", lazy="joined")
    contrato = relationship("Contrato", lazy="joined")
    creado_por = relationship("User", lazy="joined")

    procesada: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    procesada_en: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    __table_args__ = (
        CheckConstraint("tipo IN ('DIA','HORAS')", name="ck_inasistencias_tipo"),
        CheckConstraint(
            "(tipo = 'DIA' AND minutos_ausentes IS NULL) OR (tipo = 'HORAS' AND minutos_ausentes IS NOT NULL AND minutos_ausentes > 0)",
            name="ck_inasistencias_minutos_por_tipo",
        ),
    )

class AnticipoNomina(db.Model):
    __tablename__ = "anticipos_nominas"

    id = db.Column(db.Integer, primary_key=True)
    anio = db.Column(db.Integer, nullable=False)
    mes = db.Column(db.Integer, nullable=False)

    # guardarlo normalizado (UPPER/TRIM) desde la app
    centro_costo = db.Column(db.String(100), nullable=False)

    estado = db.Column(db.String(20), nullable=False, default="BORRADOR")
    # BORRADOR / ENVIADA / VISADA / CERRADA

    origen_archivo = db.Column(db.String(255))
    importado_por = db.Column(db.Integer, db.ForeignKey("users.id"))
    importado_en = db.Column(db.DateTime)

    visado_por = db.Column(db.Integer, db.ForeignKey("users.id"))
    visado_en = db.Column(db.DateTime)

    observacion = db.Column(db.String(500))
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    detalles = db.relationship(
        "AnticipoDetalle",
        back_populates="nomina",
        cascade="all, delete-orphan",
        lazy="selectin",
    )

    __table_args__ = (
        db.UniqueConstraint("anio", "mes", "centro_costo", name="uq_anticipos_nominas_periodo_cc"),
    )


class AnticipoDetalle(db.Model):
    __tablename__ = "anticipos_detalles"

    id = db.Column(db.Integer, primary_key=True)
    nomina_id = db.Column(db.Integer, db.ForeignKey("anticipos_nominas.id"), nullable=False)
    nomina = db.relationship("AnticipoNomina", back_populates="detalles")

    trabajador_id = db.Column(db.Integer, db.ForeignKey("trabajadores.id"))
    contrato_id = db.Column(db.Integer, db.ForeignKey("contratos.id"), nullable=True, index=True)
    obra_id = db.Column(db.Integer, db.ForeignKey("obras.id"))

    rut = db.Column(db.String(20))
    nombre_completo = db.Column(db.String(160))
    nombre_obra = db.Column(db.String(160))

    centro_costo = db.Column(db.String(100), nullable=False)

    monto = db.Column(db.Numeric(12, 2), nullable=False, default=0)
    observacion = db.Column(db.String(300))
    estado_linea = db.Column(db.String(20), nullable=False, default="OK")
    # OK / NO_ENCONTRADO / OBRA_NO_CALZA / DUPLICADA / OBSERVADA / AMBIGUO_CONTRATO / SIN_CONTRATO_EN_PERIODO

    trabajador = db.relationship("Trabajador", lazy="joined")
    contrato = db.relationship("Contrato", lazy="joined")
    obra = db.relationship("Obra", lazy="joined")

    __table_args__ = (
        db.Index("ix_anticipos_detalles_nomina_contrato", "nomina_id", "contrato_id"),
    )

# ==========================
# HORAS EXTRAS
# ==========================

class HorasExtra(db.Model):
    __tablename__ = "horas_extras"

    id = db.Column(db.Integer, primary_key=True)

    trabajador_id = db.Column(db.Integer, ForeignKey("trabajadores.id"), nullable=False, index=True)
    obra_id = db.Column(db.Integer, ForeignKey("obras.id"), nullable=False, index=True)

    fecha = db.Column(db.Date, nullable=False, index=True)
    hora_inicio = db.Column(db.Time, nullable=False)
    hora_termino = db.Column(db.Time, nullable=False)

    minutos_totales = db.Column(db.Integer, nullable=False, default=0)

    motivo = db.Column(db.Text, nullable=True)

    estado = db.Column(db.String(20), nullable=False, default="PENDIENTE", index=True)
    autorizado_por = db.Column(db.String(120), nullable=True)
    observacion_revision = db.Column(db.Text, nullable=True)

    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    trabajador = relationship("Trabajador")
    obra = relationship("Obra")

    remu_procesada = db.Column(
        db.Boolean,
        nullable=False,
        default=False,
        server_default=text("false"),
    )
    remu_procesada_en = db.Column(db.DateTime, nullable=True)
    remu_procesada_por = db.Column(db.String(120), nullable=True)

    __table_args__ = (
        CheckConstraint("minutos_totales >= 0", name="ck_horas_extras_minutos_no_neg"),
    )

# ==========================
# PACTOS DE HORAS EXTRA
# ==========================

class PactoHorasExtra(db.Model):
    __tablename__ = "pactos_horas_extra"

    id = db.Column(db.Integer, primary_key=True)

    contrato_id = db.Column(db.Integer, db.ForeignKey("contratos.id"), nullable=False, index=True)
    trabajador_id = db.Column(db.Integer, db.ForeignKey("trabajadores.id"), nullable=False, index=True)
    empleador_id = db.Column(db.Integer, db.ForeignKey("empleadores.id"), nullable=True, index=True)
    obra_id = db.Column(db.Integer, db.ForeignKey("obras.id"), nullable=True, index=True)

    fecha_inicio = db.Column(db.Date, nullable=False, index=True)
    fecha_termino = db.Column(db.Date, nullable=False, index=True)
    fecha_emision = db.Column(db.Date, nullable=False, default=date.today, index=True)

    observaciones = db.Column(db.Text, nullable=True)

    formato = db.Column(db.String(10), nullable=False, default="AMBOS")
    # DOCX / PDF / AMBOS (por ahora emitiremos ambos)

    estado = db.Column(db.String(20), nullable=False, default="BORRADOR", index=True)
    # BORRADOR / EMITIDO / ANULADO

    docx_nombre = db.Column(db.String(255), nullable=True)
    docx_ruta = db.Column(db.Text, nullable=True)

    pdf_nombre = db.Column(db.String(255), nullable=True)
    pdf_ruta = db.Column(db.Text, nullable=True)

    meta = db.Column(JSON().with_variant(JSONB, "postgresql"), nullable=True)

    creado_en = db.Column(db.DateTime(timezone=True), server_default=func.now(), nullable=False)
    actualizado_en = db.Column(
        db.DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    contrato = db.relationship(
        "Contrato",
        backref=db.backref("pactos_horas_extra", lazy=True),
    )
    trabajador = db.relationship(
        "Trabajador",
        backref=db.backref("pactos_horas_extra", lazy=True),
    )
    empleador = db.relationship(
        "Empleador",
        backref=db.backref("pactos_horas_extra", lazy=True),
    )
    obra = db.relationship(
        "Obra",
        backref=db.backref("pactos_horas_extra", lazy=True),
    )

    @property
    def vigente(self) -> bool:
        if self.estado != "EMITIDO":
            return False
        hoy = date.today()
        return self.fecha_inicio <= hoy <= self.fecha_termino

    @property
    def vencido(self) -> bool:
        if self.estado == "ANULADO":
            return False
        return self.fecha_termino < date.today()

    @property
    def dias_para_expirar(self) -> int | None:
        if not self.fecha_termino:
            return None
        return (self.fecha_termino - date.today()).days

    @property
    def nombre_display(self) -> str:
        if not self.trabajador:
            return f"Pacto horas extra #{self.id}"

        partes = [
            (self.trabajador.ap_paterno or "").strip(),
            (self.trabajador.ap_materno or "").strip(),
            (self.trabajador.nombres or "").strip(),
        ]
        return " ".join([p for p in partes if p]).strip() or f"Pacto horas extra #{self.id}"

    def __repr__(self):
        return (
            f"<PactoHorasExtra id={self.id} trabajador={self.trabajador_id} "
            f"inicio={self.fecha_inicio} termino={self.fecha_termino} estado={self.estado}>"
        )

# ==========================
# Solicitud de Fondos (MVP)
# ==========================

class SolicitudFondos(db.Model):
    __tablename__ = "solicitudes_fondos"

    id = db.Column(db.Integer, primary_key=True)

    # ✅ Ahora la solicitud es POR CENTRO DE COSTO (manda esto)
    centro_costo = db.Column(db.String(100), nullable=False, index=True)

    # ✅ Obra queda solo como referencia opcional (útil para contexto)
    obra_id = db.Column(db.Integer, db.ForeignKey("obras.id"), nullable=True, index=True)
    obra = db.relationship("Obra", lazy="joined")

    numero = db.Column(db.Integer, nullable=False)  # correlativo por centro de costo
    fecha_solicitud = db.Column(db.Date, nullable=False)

    periodo_tipo = db.Column(db.String(20), nullable=False)  # QUINCENA / FIN_MES / OTRO
    periodo_desde = db.Column(db.Date, nullable=True)
    periodo_hasta = db.Column(db.Date, nullable=True)

    estado = db.Column(db.String(20), nullable=False, default="BORRADOR", index=True)
    # BORRADOR / ENVIADA / APROBADA / RECHAZADA / PAGADA

    observaciones = db.Column(db.Text, nullable=True)

    creado_por_user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    creado_por = db.relationship("User", foreign_keys=[creado_por_user_id], lazy="joined")

    creado_en = db.Column(db.DateTime(timezone=True), server_default=func.now(), nullable=False)
    actualizado_en = db.Column(
        db.DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    items = db.relationship(
        "SolicitudFondosItem",
        back_populates="solicitud",
        cascade="all, delete-orphan",
        lazy="selectin",
        order_by="SolicitudFondosItem.seccion, SolicitudFondosItem.orden, SolicitudFondosItem.id",
    )

    __table_args__ = (
        # ✅ correlativo único POR CENTRO DE COSTO
        db.UniqueConstraint("centro_costo", "numero", name="uq_solicitudes_fondos_cc_numero"),
        db.CheckConstraint(
            "periodo_tipo IN ('QUINCENA','FIN_MES','OTRO')",
            name="ck_solicitud_fondos_periodo_tipo",
        ),
        db.CheckConstraint(
            "estado IN ('BORRADOR','ENVIADA','APROBADA','RECHAZADA','PAGADA')",
            name="ck_solicitud_fondos_estado",
        ),
    )

    def __repr__(self):
        return (
            f"<SolicitudFondos id={self.id} cc={self.centro_costo} "
            f"obra={self.obra_id} nro={self.numero} estado={self.estado}>"
        )


class SolicitudFondosItem(db.Model):
    __tablename__ = "solicitudes_fondos_items"

    id = db.Column(db.Integer, primary_key=True)

    solicitud_id = db.Column(db.Integer, db.ForeignKey("solicitudes_fondos.id"), nullable=False, index=True)

    seccion = db.Column(db.String(10), nullable=False, index=True)
    # REMU / REND / TERC / VAR

    # Beneficiario libre (si no está ligado a tercero/trabajador)
    beneficiario_nombre = db.Column(db.String(200), nullable=True)
    beneficiario_rut_num = db.Column(db.Integer, nullable=True)
    beneficiario_dv = db.Column(db.String(2), nullable=True)

    contrato_id = db.Column(db.Integer, db.ForeignKey("contratos.id", ondelete="SET NULL"), nullable=True, index=True)
    contrato = db.relationship("Contrato", lazy="joined")


    tercero_id = db.Column(db.Integer, db.ForeignKey("terceros.id"), nullable=True, index=True)
    trabajador_id = db.Column(db.Integer, db.ForeignKey("trabajadores.id"), nullable=True, index=True)

    monto = db.Column(db.Numeric(14, 2), nullable=False, default=0)

    tipo_pago = db.Column(db.String(40), nullable=True)      # transferencia/cheque/etc
    nro_documento = db.Column(db.String(40), nullable=True)  # ahora: "TIPO|NUM" (TERC/VAR) o legacy libre
    concepto = db.Column(db.String(80), nullable=True)       # etiqueta corta
    descripcion = db.Column(db.String(255), nullable=True)   # detalle
    control_interno = db.Column(db.String(60), nullable=True)

    orden = db.Column(db.Integer, nullable=False, default=1)

    creado_en = db.Column(db.DateTime(timezone=True), server_default=func.now(), nullable=False)
    actualizado_en = db.Column(
        db.DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    # ==========================
    # Origen: Anticipos (integración REMU quincena)
    # ==========================
    anticipo_nomina_id = db.Column(
        db.Integer,
        db.ForeignKey("anticipos_nominas.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    anticipo_detalle_id = db.Column(
        db.Integer,
        db.ForeignKey("anticipos_detalles.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    # ✅ Evita integrar el mismo anticipo_detalle 2 veces en la misma solicitud
    db.UniqueConstraint("solicitud_id", "anticipo_detalle_id", name="uq_sf_item_anticipo_detalle"),

    # ==========================
    # Origen: Sueldos (integración REMU)
    # ==========================
    sueldo_nomina_id = db.Column(
        db.Integer,
        db.ForeignKey("sueldos_nominas.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    sueldo_detalle_id = db.Column(
        db.Integer,
        db.ForeignKey("sueldos_detalles.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    __table_args__ = (
        db.CheckConstraint(
            "seccion IN ('REMU','REND','TERC','VAR')",
            name="ck_solicitud_fondos_item_seccion",
        ),
        db.CheckConstraint(
            "(seccion = 'REND') OR (monto >= 0)",
            name="ck_solicitud_fondos_item_monto_no_neg",
        ),

        # ✅ Evita integrar el mismo sueldo_detalle 2 veces en la misma solicitud
        db.UniqueConstraint("solicitud_id", "sueldo_detalle_id", name="uq_sf_item_sueldo_detalle"),
        db.UniqueConstraint(
            "solicitud_id", "seccion", "concepto", "trabajador_id", "contrato_id", "control_interno",
            name="uq_sf_item_remu_trabajador_contrato_periodo",
        ),
    )

    # ==========================
    # Relaciones
    # ==========================
    solicitud = db.relationship("SolicitudFondos", back_populates="items")

    tercero = db.relationship("Tercero", lazy="joined")
    trabajador = db.relationship("Trabajador", lazy="joined")

    sueldo_nomina = db.relationship("SueldoNomina", foreign_keys=[sueldo_nomina_id], lazy="joined")

    # Relación "origen": este SF item proviene de este detalle de sueldo
    sueldo_detalle_origen = db.relationship(
        "SueldoDetalle",
        foreign_keys=[sueldo_detalle_id],
        back_populates="sf_item_origen",
        lazy="joined",
    )

    anticipo_nomina = db.relationship("AnticipoNomina", foreign_keys=[anticipo_nomina_id], lazy="joined")

    anticipo_detalle_origen = db.relationship(
        "AnticipoDetalle",
        foreign_keys=[anticipo_detalle_id],
        lazy="joined",
    )

    # ============================================================
    # Diccionarios “de negocio” (labels bonitos para UI)
    # ============================================================
    TIPO_PAGO_LABELS = {
        "TRANSFERENCIA": "Transferencia",
        "NOMINA_2": "Nómina 2",
    }

    TIPO_DOCUMENTO_LABELS = {
        "FACTURA": "Factura",
        "FACTURA_EXENTA": "Factura exenta",
        "BOLETA": "Boleta",
        "BOLETA_HONORARIOS": "Boleta de Honorarios",
        "COMPROBANTE": "Comprobante",
        "RECIBO": "Recibo",
        "ORDEN_COMPRA": "Orden de compra",
        "NOTA_VENTA": "Nota de venta",
        "GUIA_DESPACHO": "Guía de despacho",
        "VOUCHER": "Voucher / Transbank",
        "LIQUIDACION": "Liquidación",
        "CONTRATO": "Contrato",
        "SIN_DOCUMENTO": "Sin documento",
    }

    CONCEPTO_LABELS = {
        "CONTRATISTA": "Contratista",
        "SERVICIOS": "Servicios",
        "TRATOS_INTERNOS": "Tratos internos",
        "PROVEEDORES": "Proveedores",
        "PROVISIONES": "Provisiones",
        "FINIQUITOS": "Finiquitos",
        "OTROS": "Otros",
    }

    @property
    def beneficiario_display(self) -> str:
        if self.trabajador is not None:
            return f"{self.trabajador.ap_paterno} {self.trabajador.ap_materno or ''}, {self.trabajador.nombres}".strip()
        if self.tercero is not None:
            return self.tercero.nombre_display
        return (self.beneficiario_nombre or "-").strip() or "-"

    # ============================================================
    # Documento: nro_documento = "TIPO|NUM" (nuevo) o legacy (texto)
    # ============================================================
    @property
    def documento_tipo(self) -> str | None:
        v = (self.nro_documento or "").strip()
        if not v or "|" not in v:
            return None
        tipo = v.split("|", 1)[0].strip().upper()
        return tipo or None

    @property
    def documento_numero(self) -> str | None:
        v = (self.nro_documento or "").strip()
        if not v or "|" not in v:
            return None
        num = v.split("|", 1)[1].strip()
        return num or None

    @property
    def documento_tipo_label(self) -> str:
        tipo = self.documento_tipo
        if not tipo:
            return "Documento"
        return self.TIPO_DOCUMENTO_LABELS.get(tipo, tipo.title().replace("_", " "))

    @property
    def documento_numero_label(self) -> str:
        v = (self.nro_documento or "").strip()
        if not v:
            return "Sin Nro. Doc."

        if "|" in v:
            num = self.documento_numero
            return num if num else "Sin Nro. Doc."

        return v

    @property
    def documento_display(self) -> str:
        return f"{self.documento_tipo_label} · {self.documento_numero_label}"

    @property
    def tipo_pago_label(self) -> str:
        v = (self.tipo_pago or "").strip().upper()
        if not v:
            return "-"
        return self.TIPO_PAGO_LABELS.get(v, v.title().replace("_", " "))

    @property
    def concepto_label(self) -> str:
        v = (self.concepto or "").strip().upper()
        if not v:
            return "-"
        return self.CONCEPTO_LABELS.get(v, v.title().replace("_", " "))

    def __repr__(self):
        return f"<SolicitudFondosItem id={self.id} sol={self.solicitud_id} seccion={self.seccion} monto={self.monto}>"


# ==========================
# Rendiciones de gastos
# ==========================
class RendicionCentroCostoAutorizado(db.Model):
    __tablename__ = "rendiciones_cc_autorizados"

    id = sa.Column(sa.Integer, primary_key=True)
    centro_costo = sa.Column(sa.String(100), nullable=False, index=True)

    user_id = sa.Column(sa.Integer, sa.ForeignKey("users.id"), nullable=False, index=True)
    vigente = sa.Column(sa.Boolean, nullable=False, server_default=sa.text("true"))

    created_at = sa.Column(sa.DateTime, nullable=False, server_default=sa.func.now())
    created_by_user_id = sa.Column(sa.Integer, sa.ForeignKey("users.id"), nullable=True)

    user = relationship("User", foreign_keys=[user_id])
    created_by = relationship("User", foreign_keys=[created_by_user_id])

    __table_args__ = (
        sa.UniqueConstraint("centro_costo", "user_id", name="uq_rendiciones_cc_user"),
    )


class RendicionGasto(db.Model):
    __tablename__ = "rendiciones_gastos"

    id = sa.Column(sa.Integer, primary_key=True)

    centro_costo = sa.Column(sa.String(100), nullable=False, index=True)
    numero = sa.Column(sa.Integer, nullable=False)

    obra_id = sa.Column(sa.Integer, sa.ForeignKey("obras.id"), nullable=True, index=True)
    solicitud_fondos_id = sa.Column(sa.Integer, sa.ForeignKey("solicitudes_fondos.id"), nullable=True, index=True)

    fecha_rendicion = sa.Column(sa.Date, nullable=False, server_default=sa.func.current_date())
    periodo_desde = sa.Column(sa.Date, nullable=True)
    periodo_hasta = sa.Column(sa.Date, nullable=True)

    estado = sa.Column(sa.String(20), nullable=False, server_default="BORRADOR", index=True)
    observaciones = sa.Column(sa.Text, nullable=True)

    creado_por_user_id = sa.Column(sa.Integer, sa.ForeignKey("users.id"), nullable=False, index=True)
    creado_en = sa.Column(sa.DateTime, nullable=False, server_default=sa.func.now())
    actualizado_en = sa.Column(sa.DateTime, nullable=False, server_default=sa.func.now(), onupdate=sa.func.now())

    obra = relationship("Obra")
    solicitud = relationship("SolicitudFondos")
    creado_por = relationship("User", foreign_keys=[creado_por_user_id])

    items = relationship(
        "RendicionGastoItem",
        back_populates="rendicion",
        cascade="all, delete-orphan",
        order_by="RendicionGastoItem.orden.asc()",
    )

    __table_args__ = (
        sa.UniqueConstraint("centro_costo", "numero", name="uq_rendiciones_cc_numero"),
    )


class RendicionGastoItem(db.Model):
    __tablename__ = "rendiciones_gastos_items"

    id = sa.Column(sa.Integer, primary_key=True)
    rendicion_id = sa.Column(sa.Integer, sa.ForeignKey("rendiciones_gastos.id", ondelete="CASCADE"), nullable=False, index=True)

    orden = sa.Column(sa.Integer, nullable=False, server_default="1")

    fecha = sa.Column(sa.Date, nullable=True)

    detalle = sa.Column(sa.String(240), nullable=False)  # “concepto / detalle”
    descripcion = sa.Column(sa.String(500), nullable=True)

    tipo_doc = sa.Column(sa.String(30), nullable=True)   # FACTURA/BOLETA/COMPROBANTE/OTRO
    nro_doc = sa.Column(sa.String(80), nullable=True)

    proveedor = sa.Column(sa.String(240), nullable=True)  # libre (si después quieren tercero_id lo sumamos)
    monto = sa.Column(sa.Numeric(14, 2), nullable=False, server_default="0")

    rendicion = relationship("RendicionGasto", back_populates="items")

class DesvinculacionDocInputs(db.Model):
    __tablename__ = "desvinculacion_doc_inputs"

    id = db.Column(db.Integer, primary_key=True)
    desvinculacion_id = db.Column(db.Integer, db.ForeignKey("desvinculaciones.id", ondelete="CASCADE"), nullable=False)
    doc_tipo = db.Column(db.String(30), nullable=False)
    inputs = db.Column(JSON().with_variant(JSONB, "postgresql"), nullable=False, default=dict)

    creado_en = db.Column(db.DateTime(timezone=True), server_default=db.func.now(), nullable=False)
    actualizado_en = db.Column(db.DateTime(timezone=True), server_default=db.func.now(), nullable=False)

    __table_args__ = (
        db.UniqueConstraint("desvinculacion_id", "doc_tipo", name="uq_desv_doc_inputs_desv_tipo"),
        db.Index("ix_desv_doc_inputs_desvinculacion_id", "desvinculacion_id"),
        db.Index("ix_desv_doc_inputs_doc_tipo", "doc_tipo"),
    )

# ==========================
# Certificados laborales
# ==========================

class CertificadoLaboral(db.Model):
    __tablename__ = "certificados_laborales"

    id = db.Column(db.Integer, primary_key=True)

    trabajador_id = db.Column(db.Integer, db.ForeignKey("trabajadores.id"), nullable=False, index=True)
    contrato_id = db.Column(db.Integer, db.ForeignKey("contratos.id"), nullable=True, index=True)

    empleador_id = db.Column(db.Integer, db.ForeignKey("empleadores.id"), nullable=True, index=True)
    obra_id = db.Column(db.Integer, db.ForeignKey("obras.id"), nullable=True, index=True)

    # ANTIGUEDAD / VIGENCIA / OTRO (y después puedes expandir)
    tipo = db.Column(db.String(30), nullable=False, index=True)

    # Texto libre: “para presentar a banco”, “trámite arriendo”, etc.
    objetivo = db.Column(db.String(255), nullable=True)

    fecha_emision = db.Column(db.Date, nullable=False, default=date.today, index=True)

    estado = db.Column(db.String(20), nullable=False, default="BORRADOR", index=True)
    # BORRADOR / EMITIDO / ANULADO

    # Archivo / Nextcloud
    docx_nombre = db.Column(db.String(255), nullable=True)
    docx_ruta = db.Column(db.Text, nullable=True)

    pdf_nombre = db.Column(db.String(255), nullable=True)
    pdf_ruta = db.Column(db.Text, nullable=True)

    creado_por_user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True, index=True)
    creado_por = db.relationship("User", foreign_keys=[creado_por_user_id], lazy="joined")

    meta = db.Column(JSON().with_variant(JSONB, "postgresql"), nullable=True)

    creado_en = db.Column(db.DateTime(timezone=True), server_default=func.now(), nullable=False)
    actualizado_en = db.Column(db.DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    trabajador = db.relationship("Trabajador", lazy="joined")
    contrato = db.relationship("Contrato", lazy="joined")
    empleador = db.relationship("Empleador", lazy="joined")
    obra = db.relationship("Obra", lazy="joined")

    __table_args__ = (
        db.CheckConstraint("tipo IN ('ANTIGUEDAD','VIGENCIA','OTRO')", name="ck_certificados_tipo"),
        db.CheckConstraint("estado IN ('BORRADOR','EMITIDO','ANULADO')", name="ck_certificados_estado"),
        db.Index("ix_certificados_trab_tipo_fecha", "trabajador_id", "tipo", "fecha_emision"),
    )

    def __repr__(self):
        return f"<CertificadoLaboral {self.id} trab={self.trabajador_id} tipo={self.tipo} estado={self.estado}>"


# ==========================
# Sueldos (Nómina líquido a pago)
# ==========================

class SueldoNomina(db.Model):
    """
    Nómina de sueldos por período, empleador pagador y centro de costo.
    Similar a AnticipoNomina, pero orientada a líquido a pago.

    Clave funcional:
      - Una nómina por (anio, mes, centro_costo, empleador_id)
      - El detalle puede tener múltiples filas por trabajador si hay múltiples contratos (contrato_id).
    """
    __tablename__ = "sueldos_nominas"

    id = db.Column(db.Integer, primary_key=True)

    anio = db.Column(db.Integer, nullable=False, index=True)
    mes = db.Column(db.Integer, nullable=False, index=True)

    # En tu sistema centro_costo suele ser String(100)
    centro_costo = db.Column(db.String(100), nullable=False, index=True)

    # Empleador pagador (tabla real: empleadores)
    empleador_id = db.Column(db.Integer, db.ForeignKey("empleadores.id"), nullable=False, index=True)
    empleador = db.relationship("Empleador", lazy="joined")

    estado = db.Column(db.String(30), nullable=False, default="BORRADOR", index=True)
    # Sugeridos: BORRADOR / ENVIADA / VISADA / CERRADA (igual que anticipos, si quieres)

    # Origen / trazabilidad
    origen_archivo = db.Column(db.String(255), nullable=True)
    origen = db.Column(db.String(30), nullable=True)

    importado_por = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    importado_en = db.Column(db.DateTime, nullable=True, default=datetime.utcnow)

    visado_por = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    visado_en = db.Column(db.DateTime, nullable=True)

    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    detalles = db.relationship(
        "SueldoDetalle",
        back_populates="nomina",
        cascade="all, delete-orphan",
        lazy="selectin",
    )

    __table_args__ = (
        db.UniqueConstraint(
            "anio", "mes", "centro_costo", "empleador_id",
            name="uq_sueldos_nominas_periodo_cc_empleador",
        ),
        db.Index("ix_sueldos_nominas_periodo", "anio", "mes"),
    )

    @property
    def periodo_str(self) -> str:
        return f"{int(self.anio):04d}-{int(self.mes):02d}"

    def __repr__(self):
        return f"<SueldoNomina id={self.id} {self.periodo_str} cc={self.centro_costo} empleador={self.empleador_id} estado={self.estado}>"


class SueldoDetalle(db.Model):
    __tablename__ = "sueldos_detalles"

    id = db.Column(db.Integer, primary_key=True)

    nomina_id = db.Column(db.Integer, db.ForeignKey("sueldos_nominas.id"), nullable=False, index=True)

    trabajador_id = db.Column(db.Integer, db.ForeignKey("trabajadores.id"), nullable=True, index=True)
    contrato_id = db.Column(db.Integer, db.ForeignKey("contratos.id"), nullable=True, index=True)
    obra_id = db.Column(db.Integer, db.ForeignKey("obras.id"), nullable=True, index=True)

    centro_costo = db.Column(db.String(100), nullable=True, index=True)

    # Snapshot desde importación
    rut = db.Column(db.String(20), nullable=True, index=True)
    nombre_completo = db.Column(db.String(255), nullable=True)
    nombre_obra = db.Column(db.String(255), nullable=True)

    # Informativos importados
    anticipo = db.Column(db.Numeric(14, 2), nullable=False, default=0)

    # Líquido a pago (operativo)
    liquido = db.Column(db.Numeric(14, 2), nullable=False, default=0)

    # Control de calidad
    estado_linea = db.Column(db.String(30), nullable=False, default="OK", index=True)
    observacion = db.Column(db.String(255), nullable=True)

    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    integrado_sf_item_id = db.Column(
        db.Integer,
        db.ForeignKey("solicitudes_fondos_items.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    integrado_en = db.Column(db.DateTime, nullable=True)
    integrado_por = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    __table_args__ = (
        db.UniqueConstraint(
            "nomina_id", "trabajador_id", "contrato_id",
            name="uq_sueldos_detalles_nomina_trabajador_contrato",
        ),
        db.Index("ix_sueldos_detalles_nomina_obra", "nomina_id", "obra_id"),
        db.Index("ix_sueldos_detalles_rut", "rut"),
    )

    nomina = db.relationship("SueldoNomina", back_populates="detalles", lazy="joined")
    trabajador = db.relationship("Trabajador", lazy="joined")
    contrato = db.relationship("Contrato", lazy="joined")
    obra = db.relationship("Obra", lazy="joined")

    integrado_por_user = db.relationship("User", foreign_keys=[integrado_por], lazy="joined")

    integrado_sf_item = db.relationship(
        "SolicitudFondosItem",
        foreign_keys=[integrado_sf_item_id],
        uselist=False,
        lazy="joined",
    )

    sf_item_origen = db.relationship(
        "SolicitudFondosItem",
        foreign_keys="SolicitudFondosItem.sueldo_detalle_id",
        back_populates="sueldo_detalle_origen",
        uselist=False,
    )

    @property
    def alcance_liquido(self):
        return (self.anticipo or 0) + (self.liquido or 0)

    def __repr__(self):
        return (
            f"<SueldoDetalle id={self.id} nomina={self.nomina_id} "
            f"trab={self.trabajador_id} contrato={self.contrato_id} "
            f"anticipo={self.anticipo} liquido={self.liquido}>"
        )


# ==========================
# Egresos (Pago extraordinario a trabajador / Externo)
# ==========================

class Egreso(db.Model):
    __tablename__ = "egresos"

    id = db.Column(db.Integer, primary_key=True)

    # ✅ correlativo global (lo asigna la secuencia en DB)
    numero = db.Column(
        db.Integer,
        nullable=False,
        server_default=text("nextval('egresos_numero_seq'::regclass)")
    )

    # ✅ ahora puede ser NULL (para externos)
    trabajador_id = db.Column(db.Integer, db.ForeignKey("trabajadores.id"), nullable=True, index=True)
    contrato_id = db.Column(db.Integer, db.ForeignKey("contratos.id"), nullable=True, index=True)

    empleador_id = db.Column(db.Integer, db.ForeignKey("empleadores.id"), nullable=True, index=True)
    obra_id = db.Column(db.Integer, db.ForeignKey("obras.id"), nullable=True, index=True)

    fecha_egreso = db.Column(db.Date, nullable=False, default=date.today, index=True)

    # BORRADOR / EMITIDO / ANULADO
    estado = db.Column(db.String(20), nullable=False, default="BORRADOR", index=True)

    motivo = db.Column(db.String(255), nullable=False)

    solicitante = db.Column(db.String(200), nullable=True)
    solicitante_cargo = db.Column(db.String(120), nullable=True)

    observaciones = db.Column(db.Text, nullable=True)

    # ✅ Beneficiario externo
    pagado_a_nombre = db.Column(db.String(200), nullable=True)
    pagado_a_rut = db.Column(db.String(20), nullable=True)

    # Archivo / Nextcloud
    docx_nombre = db.Column(db.String(255), nullable=True)
    docx_ruta = db.Column(db.Text, nullable=True)

    pdf_nombre = db.Column(db.String(255), nullable=True)
    pdf_ruta = db.Column(db.Text, nullable=True)

    creado_por_user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True, index=True)
    creado_por = db.relationship("User", foreign_keys=[creado_por_user_id], lazy="joined")

    meta = db.Column(JSON().with_variant(JSONB, "postgresql"), nullable=True)

    creado_en = db.Column(db.DateTime(timezone=True), server_default=func.now(), nullable=False)
    actualizado_en = db.Column(db.DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    trabajador = db.relationship("Trabajador", lazy="joined")
    contrato = db.relationship("Contrato", lazy="joined")
    empleador = db.relationship("Empleador", lazy="joined")
    obra = db.relationship("Obra", lazy="joined")

    items = db.relationship(
        "EgresoItem",
        back_populates="egreso",
        cascade="all, delete-orphan",
        order_by="EgresoItem.orden.asc()",
        lazy="selectin",
    )

    __table_args__ = (
        db.CheckConstraint("estado IN ('BORRADOR','EMITIDO','ANULADO')", name="ck_egresos_estado"),
        db.Index("ix_egresos_trab_fecha", "trabajador_id", "fecha_egreso"),
    )

    @property
    def es_externo(self) -> bool:
        return self.trabajador_id is None and bool((self.pagado_a_nombre or "").strip())

    @property
    def total(self):
        return sum([float(i.monto or 0) for i in (self.items or [])])

    def __repr__(self):
        return f"<Egreso {self.id} N={self.numero} trab={self.trabajador_id} fecha={self.fecha_egreso} estado={self.estado}>"


class EgresoItem(db.Model):
    __tablename__ = "egresos_items"

    id = db.Column(db.Integer, primary_key=True)

    egreso_id = db.Column(db.Integer, db.ForeignKey("egresos.id", ondelete="CASCADE"), nullable=False, index=True)
    orden = db.Column(db.Integer, nullable=False, default=1)

    item = db.Column(db.String(255), nullable=True)
    monto = db.Column(db.Numeric(14, 2), nullable=False, default=0)

    egreso = db.relationship("Egreso", back_populates="items")

    __table_args__ = (
        db.CheckConstraint("orden >= 1 AND orden <= 5", name="ck_egresos_items_orden_1_5"),
        db.CheckConstraint("monto >= 0", name="ck_egresos_items_monto_no_neg"),
        db.UniqueConstraint("egreso_id", "orden", name="uq_egresos_items_egreso_orden"),
    )

    def __repr__(self):
        return f"<EgresoItem egreso={self.egreso_id} orden={self.orden} monto={self.monto}>"


# ==========================
# Acuerdos de Pago (Préstamos / Herramientas / EPP mejorado)
# ==========================

import enum


class TipoAcuerdoPago(enum.Enum):
    DINERO = "DINERO"
    HERRAMIENTAS = "HERRAMIENTAS"
    EPP_DIFERENCIA = "EPP_DIFERENCIA"
    EXTRAVIO_EQUIPOS = "EXTRAVIO_EQUIPOS"
    OTROS = "OTROS"


class AcuerdoPago(db.Model):
    __tablename__ = "acuerdos_pago"

    id = db.Column(db.Integer, primary_key=True)

    # ✅ correlativo global (igual a Egresos): requiere secuencia en DB
    numero = db.Column(
        db.Integer,
        nullable=False,
        server_default=text("nextval('acuerdos_pago_numero_seq'::regclass)")
    )

    # Asociaciones principales
    trabajador_id = db.Column(db.Integer, db.ForeignKey("trabajadores.id"), nullable=False, index=True)
    contrato_id = db.Column(db.Integer, db.ForeignKey("contratos.id"), nullable=True, index=True)

    empleador_id = db.Column(db.Integer, db.ForeignKey("empleadores.id"), nullable=True, index=True)
    obra_id = db.Column(db.Integer, db.ForeignKey("obras.id"), nullable=True, index=True)

    # Fecha del acuerdo (emisión/firma referencial)
    fecha_acuerdo = db.Column(db.Date, nullable=False, default=date.today, index=True)

    # Tipo de acuerdo (enum)
    tipo = db.Column(
        db.Enum(TipoAcuerdoPago, name="tipo_acuerdo_pago_enum"),
        nullable=False,
        index=True,
    )

    # Resumen / motivo (lo que el usuario entiende rápido)
    # Ej: "Préstamo personal", "Compra de herramientas", "Diferencia zapatos premium"
    concepto = db.Column(db.String(255), nullable=False)

    # Monto total del acuerdo (siempre existe incluso en herramientas/EPP diferencia)
    monto_total = db.Column(db.Numeric(14, 2), nullable=False, default=0)

    # Modalidad principal (por ahora conservadora: descuento por remuneración)
    # Si luego agregan otras modalidades, esto se puede ampliar.
    modalidad = db.Column(db.String(40), nullable=False, default="DESCUENTO_LIQUIDACION")

    # Cuotas / descuento
    cuotas = db.Column(db.Integer, nullable=False, default=1)
    monto_cuota = db.Column(db.Numeric(14, 2), nullable=False, default=0)

    # Mes inicio descuento: formato "YYYY-MM" (simple y útil en UI)
    mes_inicio_descuento = db.Column(db.String(7), nullable=True)  # ej: "2026-02"

    observaciones = db.Column(db.Text, nullable=True)

    # Estado del documento
    # BORRADOR: editable
    # EMITIDO: ya generó DOCX/PDF con folio (idealmente inmutable)
    # FIRMADO: firmado (manual o e-firma)
    # PAGADO: saldo 0 (futuro, si integran control)
    # ANULADO: sin efecto
    estado = db.Column(db.String(20), nullable=False, default="BORRADOR", index=True)

    # Archivos / Nextcloud (mismo patrón que Egreso/Certificado)
    docx_nombre = db.Column(db.String(255), nullable=True)
    docx_ruta = db.Column(db.Text, nullable=True)

    pdf_nombre = db.Column(db.String(255), nullable=True)
    pdf_ruta = db.Column(db.Text, nullable=True)

    # Auditoría
    creado_por_user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True, index=True)
    creado_por = db.relationship("User", foreign_keys=[creado_por_user_id], lazy="joined")

    meta = db.Column(JSON().with_variant(JSONB, "postgresql"), nullable=True)

    creado_en = db.Column(db.DateTime(timezone=True), server_default=func.now(), nullable=False)
    actualizado_en = db.Column(db.DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    # Relaciones
    trabajador = db.relationship("Trabajador", lazy="joined")
    contrato = db.relationship("Contrato", lazy="joined")
    empleador = db.relationship("Empleador", lazy="joined")
    obra = db.relationship("Obra", lazy="joined")

    __table_args__ = (
        db.CheckConstraint("estado IN ('BORRADOR','EMITIDO','FIRMADO','PAGADO','ANULADO')", name="ck_acuerdos_pago_estado"),
        db.CheckConstraint("monto_total >= 0", name="ck_acuerdos_pago_monto_total_no_neg"),
        db.CheckConstraint("cuotas >= 1", name="ck_acuerdos_pago_cuotas_min_1"),
        db.CheckConstraint("monto_cuota >= 0", name="ck_acuerdos_pago_monto_cuota_no_neg"),
        db.CheckConstraint("modalidad IN ('DESCUENTO_LIQUIDACION')", name="ck_acuerdos_pago_modalidad"),
        db.Index("ix_acuerdos_pago_trab_fecha", "trabajador_id", "fecha_acuerdo"),
        db.Index("ix_acuerdos_pago_tipo_estado", "tipo", "estado"),
    )

    # --------------------------
    # Helpers (Nombre archivo + Nextcloud)
    # --------------------------
    @property
    def trabajador_nombre_archivo(self) -> str:
        """
        Formato requerido:
          <Ap. Paterno Ap. Materno Nombres>
        """
        t = self.trabajador
        if not t:
            return "Trabajador"
        ap_pat = (t.ap_paterno or "").strip()
        ap_mat = (t.ap_materno or "").strip()
        noms = (t.nombres or "").strip()
        return " ".join([x for x in [ap_pat, ap_mat, noms] if x]).strip() or "Trabajador"

    @property
    def nombre_archivo_base(self) -> str:
        """
        Formato corporativo acordado:
          <AAAA-MM-DD> Acuerdo de Pago - <Ap. Paterno Ap. Materno Nombres>
        """
        f = self.fecha_acuerdo or date.today()
        return f"{f.isoformat()} Acuerdo de Pago - {self.trabajador_nombre_archivo}"

    @property
    def carpeta_destino_nextcloud(self) -> str | None:
        """
        /CENTRO_COSTO/Laboral/Trabajadores/<Persona>/ACUERDOS
        Usamos el empleador si está disponible, sino el preferente del trabajador.
        """
        if not self.trabajador:
            return None

        emp = self.empleador
        if emp is None:
            emp = self.trabajador.empleador_preferente

        if emp is None:
            return None

        base = self.trabajador.ruta_nextcloud(emp.razon_social)
        return f"{base}/ACUERDOS"

    @property
    def ruta_docx_completa(self) -> str | None:
        carpeta = self.carpeta_destino_nextcloud
        if not carpeta or not self.docx_nombre:
            return None
        return f"{carpeta}/{self.docx_nombre}"

    @property
    def ruta_pdf_completa(self) -> str | None:
        carpeta = self.carpeta_destino_nextcloud
        if not carpeta or not self.pdf_nombre:
            return None
        return f"{carpeta}/{self.pdf_nombre}"

    emitido_version = db.Column(db.Integer, nullable=False, default=0)

    def __repr__(self):
        return (
            f"<AcuerdoPago id={self.id} N={self.numero} trab={self.trabajador_id} "
            f"fecha={self.fecha_acuerdo} tipo={self.tipo} estado={self.estado}>"
        )

# ==========================
# Vacaciones (MVP)
# ==========================

class Vacacion(db.Model):
    __tablename__ = "vacaciones"

    id = db.Column(db.Integer, primary_key=True)

    contrato_id = db.Column(db.Integer, db.ForeignKey("contratos.id"), nullable=False, index=True)
    contrato = db.relationship("Contrato", lazy="joined")

    corr_contrato = db.Column(db.Integer, nullable=False)  # Comprobante Nro. por contrato

    fecha_emision = db.Column(db.Date, nullable=False, default=date.today, index=True)
    fecha_inicio = db.Column(db.Date, nullable=False, index=True)
    fecha_termino = db.Column(db.Date, nullable=False, index=True)
    fecha_retorno = db.Column(db.Date, nullable=False, index=True)

    dias_habiles = db.Column(db.Integer, nullable=False, default=0)

    saldo_prev = db.Column(db.Numeric(6, 2), nullable=False, default=0)
    saldo_post = db.Column(db.Numeric(6, 2), nullable=False, default=0)

    observaciones = db.Column(db.Text, nullable=True)

    estado = db.Column(db.String(20), nullable=False, default="BORRADOR", index=True)

    es_anticipo = db.Column(db.Boolean, nullable=False, default=False)
    # BORRADOR / EMITIDO / ANULADO

    # Archivo / Nextcloud (mismo patrón que Egreso/Certificado)
    docx_nombre = db.Column(db.String(255), nullable=True)
    docx_ruta = db.Column(db.Text, nullable=True)
    pdf_nombre = db.Column(db.String(255), nullable=True)
    pdf_ruta = db.Column(db.Text, nullable=True)

    creado_por_user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True, index=True)
    creado_por = db.relationship("User", foreign_keys=[creado_por_user_id], lazy="joined")

    creado_en = db.Column(db.DateTime(timezone=True), server_default=func.now(), nullable=False)
    actualizado_en = db.Column(db.DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    movimientos = db.relationship(
        "VacacionMovimiento",
        back_populates="vacacion",
        lazy="selectin",
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        db.UniqueConstraint("contrato_id", "corr_contrato", name="uq_vacaciones_contrato_corr"),
        db.CheckConstraint("estado IN ('BORRADOR','EMITIDO','ANULADO')", name="ck_vacaciones_estado"),
        db.CheckConstraint("dias_habiles >= 0", name="ck_vacaciones_dias"),
    )

    def __repr__(self):
        return f"<Vacacion id={self.id} contrato={self.contrato_id} corr={self.corr_contrato} {self.fecha_inicio}->{self.fecha_termino} estado={self.estado}>"


class VacacionMovimiento(db.Model):
    __tablename__ = "vacaciones_movimientos"

    id = db.Column(db.Integer, primary_key=True)

    contrato_id = db.Column(db.Integer, db.ForeignKey("contratos.id"), nullable=False, index=True)
    contrato = db.relationship("Contrato", lazy="joined")

    tipo = db.Column(db.String(10), nullable=False)  # DEVENGO / USO / AJUSTE
    fecha = db.Column(db.Date, nullable=False, default=date.today, index=True)

    dias = db.Column(db.Numeric(6, 2), nullable=False, default=0)

    vacaciones_id = db.Column(db.Integer, db.ForeignKey("vacaciones.id", ondelete="SET NULL"), nullable=True, index=True)
    vacacion = db.relationship("Vacacion", back_populates="movimientos", lazy="joined")

    detalle = db.Column(db.Text, nullable=True)

    creado_por_user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True, index=True)
    creado_por = db.relationship("User", foreign_keys=[creado_por_user_id], lazy="joined")

    creado_en = db.Column(db.DateTime(timezone=True), server_default=func.now(), nullable=False)

    __table_args__ = (
        db.CheckConstraint("tipo IN ('DEVENGO','USO','AJUSTE')", name="ck_vac_mov_tipo"),
    )

    def __repr__(self):
        return f"<VacacionMovimiento id={self.id} contrato={self.contrato_id} tipo={self.tipo} dias={self.dias} fecha={self.fecha}>"


class Feriado(db.Model):
    __tablename__ = "feriados"

    id = db.Column(db.Integer, primary_key=True)
    fecha = db.Column(db.Date, nullable=False, unique=True, index=True)
    nombre = db.Column(db.String(200), nullable=False)

    tipo = db.Column(db.String(20), nullable=False, default="LEGAL")  # LEGAL/REGIONAL/EMPRESA
    region = db.Column(db.String(40), nullable=True)

    activo = db.Column(db.Boolean, nullable=False, default=True)

    creado_en = db.Column(db.DateTime(timezone=True), server_default=func.now(), nullable=False)
    actualizado_en = db.Column(db.DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    def __repr__(self):
        return f"<Feriado {self.fecha} {self.nombre} activo={self.activo}>"
