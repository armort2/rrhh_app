from sqlalchemy.sql import func
from . import db


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

    contratos = db.relationship("Contrato", back_populates="empleador", lazy=True)
    obras = db.relationship("Obra", back_populates="empleador", lazy=True)

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

    # Relación SOLO con banco_id (la cuenta propia del trabajador)
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


class Cargo(db.Model):
    __tablename__ = "cargos"

    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(150), nullable=False)
    descripcion = db.Column(db.String(300), nullable=True)
    categoria = db.Column(db.String(100), nullable=True)  # Ej: Administrativo, Operador, Maestro, etc.

    contratos = db.relationship("Contrato", back_populates="cargo", lazy=True)
    # Nuevo: relación con trabajadores (cargo actual del trabajador)
    trabajadores = db.relationship("Trabajador", back_populates="cargo", lazy=True)

    def __repr__(self):
        return f"<Cargo {self.nombre}>"


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

    empleador_id = db.Column(db.Integer, db.ForeignKey("empleadores.id"), nullable=True)
    empleador = db.relationship("Empleador", back_populates="obras")

    estado = db.Column(db.String(20), nullable=False, default="ACTIVA")  # ACTIVA / CERRADA
    fecha_inicio = db.Column(db.Date, nullable=True)
    fecha_cierre = db.Column(db.Date, nullable=True)

    # Relación con trabajadores (obra principal actual del trabajador)
    trabajadores = db.relationship("Trabajador", back_populates="obra", lazy=True)

    # Relación con contratos
    contratos = db.relationship("Contrato", back_populates="obra", lazy=True)

    def __repr__(self):
        return f"<Obra {self.codigo} - {self.nombre}>"


# ==========================
# Trabajador
# ==========================

class Trabajador(db.Model):
    __tablename__ = "trabajadores"

    id = db.Column(db.Integer, primary_key=True)

    # Identificación
    rut = db.Column(db.String(20), unique=True, nullable=False)
    dv = db.Column(db.String(2), nullable=True)  # Por si quieres guardar el DV separado
    nombres = db.Column(db.String(100), nullable=False)
    ap_paterno = db.Column(db.String(100), nullable=False)
    ap_materno = db.Column(db.String(100), nullable=False)

    # Datos personales
    fecha_nacimiento = db.Column(db.Date, nullable=True)
    nacionalidad = db.Column(db.String(60), nullable=True)
    sexo = db.Column(db.String(10), nullable=True)          # M / F / X, etc.
    estado_civil = db.Column(db.String(30), nullable=True)  # Soltero, Casado, etc.

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

    tipo_cuenta = db.Column(db.String(20), nullable=True)      # CORRIENTE / VISTA / AHORRO / CTA_RUT
    cuenta_rut = db.Column(db.String(20), nullable=True)       # Para CTA_RUT (sin DV)
    cuenta_numero = db.Column(db.String(50), nullable=True)    # Nº de cuenta para otros tipos

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

    # Si Salud.tipo == "ISAPRE", aquí guardas el valor UF del plan
    uf_plan_salud = db.Column(db.Numeric(6, 2), nullable=True)

    # Caja de compensación
    caja_compensacion_id = db.Column(db.Integer, db.ForeignKey("cajas_compensacion.id"), nullable=True)
    caja_compensacion = db.relationship("CajaCompensacion", back_populates="trabajadores")

    # APV
    apv_activo = db.Column(db.Boolean, nullable=False, default=False)
    apv_modalidad = db.Column(db.String(20), nullable=True)    # "PORCENTAJE" / "MONTO"
    apv_valor = db.Column(db.Numeric(8, 2), nullable=True)     # % o monto según modalidad
    apv_institucion = db.Column(db.String(120), nullable=True)

    # CAV (Cuenta de Ahorro Voluntario)
    cav_activo = db.Column(db.Boolean, nullable=False, default=False)
    cav_modalidad = db.Column(db.String(20), nullable=True)    # "PORCENTAJE" / "MONTO"
    cav_valor = db.Column(db.Numeric(8, 2), nullable=True)
    cav_institucion = db.Column(db.String(120), nullable=True)

    # Cargas, condición especial
    num_cargas_familiares = db.Column(db.Integer, nullable=True)
    es_extranjero = db.Column(db.Boolean, nullable=False, default=False)
    es_discapacitado = db.Column(db.Boolean, nullable=False, default=False)
    es_pensionado = db.Column(db.Boolean, nullable=False, default=False)

    # Seguridad y salud ocupacional (campos base, se pueden extender)
    tiene_examen_preocupacional = db.Column(db.Boolean, nullable=False, default=False)
    fecha_examen_preocupacional = db.Column(db.Date, nullable=True)
    tiene_curso_altura = db.Column(db.Boolean, nullable=False, default=False)
    fecha_vencimiento_curso_altura = db.Column(db.Date, nullable=True)
    tiene_induccion_obra = db.Column(db.Boolean, nullable=False, default=False)
    fecha_induccion_obra = db.Column(db.Date, nullable=True)

    # Relación principal con obra actual
    obra_id = db.Column(db.Integer, db.ForeignKey("obras.id"), nullable=False)
    obra = db.relationship("Obra", back_populates="trabajadores")

    # Cargo actual del trabajador (tabla maestra de cargos)
    cargo_id = db.Column(db.Integer, db.ForeignKey("cargos.id"), nullable=True)
    cargo = db.relationship("Cargo", back_populates="trabajadores")

    # Estado laboral general
    estado_trabajador = db.Column(db.String(20), nullable=False, default="VIGENTE")  # VIGENTE / DESVINCULADO / SUSPENDIDO
    tipo_trabajador = db.Column(db.String(30), nullable=True)  # Directo / Subcontrato / Etc.

    fecha_ingreso_empresa = db.Column(db.Date, nullable=True)
    fecha_egreso_empresa = db.Column(db.Date, nullable=True)

    # Auditoría básica
    creado_en = db.Column(db.DateTime(timezone=True), server_default=func.now())
    actualizado_en = db.Column(db.DateTime(timezone=True), onupdate=func.now())

    # Relación con contratos
    contratos = db.relationship("Contrato", back_populates="trabajador", lazy=True)

    def __repr__(self):
        return f"<Trabajador {self.rut} - {self.nombres} {self.ap_paterno}>"


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

    # Datos contractuales
    tipo_contrato = db.Column(db.String(30), nullable=True)  # Indefinido / Plazo fijo / Faena / Etc.
    fecha_inicio = db.Column(db.Date, nullable=True)
    fecha_termino = db.Column(db.Date, nullable=True)

    jornada = db.Column(db.String(100), nullable=True)       # Descripción de jornada
    horas_semanales = db.Column(db.Integer, nullable=True)

    sueldo_base = db.Column(db.Numeric(10, 2), nullable=True)
    asignacion_movilizacion = db.Column(db.Numeric(10, 2), nullable=True)
    asignacion_colacion = db.Column(db.Numeric(10, 2), nullable=True)
    asignacion_herramientas = db.Column(db.Numeric(10, 2), nullable=True)

    estado_contrato = db.Column(db.String(20), nullable=False, default="VIGENTE")  # VIGENTE / TERMINADO
    causal_termino = db.Column(db.String(250), nullable=True)
    fecha_finiquito = db.Column(db.Date, nullable=True)

    # Auditoría
    creado_en = db.Column(db.DateTime(timezone=True), server_default=func.now())
    actualizado_en = db.Column(db.DateTime(timezone=True), onupdate=func.now())

    def __repr__(self):
        return f"<Contrato {self.id} Trabajador={self.trabajador_id}>"
    
class DocumentoLaboral(db.Model):
    __tablename__ = "documentos_laborales"

    id = db.Column(db.Integer, primary_key=True)

    # Siempre ligado a un contrato específico
    contrato_id = db.Column(db.Integer, db.ForeignKey("contratos.id"), nullable=False)
    contrato = db.relationship("Contrato", backref="documentos_laborales", lazy=True)

    # Clasificación del documento
    tipo_documento = db.Column(db.String(50), nullable=False)
    # Ej: "CONTRATO", "ANEXO", "FINIQUITO", "CARTA_AVISO", "AMONESTACION"

    fecha_documento = db.Column(db.Date, nullable=False, default=func.current_date())
    descripcion = db.Column(db.String(255), nullable=True)

    # Ruta donde quedó guardado el PDF / DOCX (por ejemplo en Nextcloud)
    ruta_archivo = db.Column(db.String(500), nullable=True)

    # Auditoría básica
    creado_en = db.Column(db.DateTime(timezone=True), server_default=func.now())
    creado_por = db.Column(db.String(50), nullable=True)

    def __repr__(self):
        return f"<DocumentoLaboral {self.tipo_documento} contrato={self.contrato_id}>"
