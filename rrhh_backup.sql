--
-- PostgreSQL database dump
--

\restrict NQx3u3ROmSvzcdJI3xFeKH75O9dRLOTXg5jTTXWvFSgc2I4jKsmvPY8MueITC02

-- Dumped from database version 16.11 (Debian 16.11-1.pgdg13+1)
-- Dumped by pg_dump version 16.11 (Debian 16.11-1.pgdg13+1)

SET statement_timeout = 0;
SET lock_timeout = 0;
SET idle_in_transaction_session_timeout = 0;
SET client_encoding = 'UTF8';
SET standard_conforming_strings = on;
SELECT pg_catalog.set_config('search_path', '', false);
SET check_function_bodies = false;
SET xmloption = content;
SET client_min_messages = warning;
SET row_security = off;

SET default_tablespace = '';

SET default_table_access_method = heap;

--
-- Name: afp; Type: TABLE; Schema: public; Owner: rrhh_user
--

CREATE TABLE public.afp (
    id integer NOT NULL,
    nombre character varying(120) NOT NULL
);


ALTER TABLE public.afp OWNER TO rrhh_user;

--
-- Name: afp_id_seq; Type: SEQUENCE; Schema: public; Owner: rrhh_user
--

CREATE SEQUENCE public.afp_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.afp_id_seq OWNER TO rrhh_user;

--
-- Name: afp_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: rrhh_user
--

ALTER SEQUENCE public.afp_id_seq OWNED BY public.afp.id;


--
-- Name: alembic_version; Type: TABLE; Schema: public; Owner: rrhh_user
--

CREATE TABLE public.alembic_version (
    version_num character varying(32) NOT NULL
);


ALTER TABLE public.alembic_version OWNER TO rrhh_user;

--
-- Name: anexos_extension_contrato; Type: TABLE; Schema: public; Owner: rrhh_user
--

CREATE TABLE public.anexos_extension_contrato (
    id integer NOT NULL,
    contrato_id integer NOT NULL,
    trabajador_id integer NOT NULL,
    empleador_id integer,
    obra_id integer,
    fecha_anexo date NOT NULL,
    fecha_termino_anterior date,
    fecha_termino_nueva date NOT NULL,
    observaciones text,
    formato character varying(10) NOT NULL,
    estado character varying(20) NOT NULL,
    docx_nombre character varying(255),
    docx_ruta text,
    pdf_nombre character varying(255),
    pdf_ruta text,
    creado_en timestamp with time zone,
    meta jsonb
);


ALTER TABLE public.anexos_extension_contrato OWNER TO rrhh_user;

--
-- Name: anexos_extension_contrato_id_seq; Type: SEQUENCE; Schema: public; Owner: rrhh_user
--

CREATE SEQUENCE public.anexos_extension_contrato_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.anexos_extension_contrato_id_seq OWNER TO rrhh_user;

--
-- Name: anexos_extension_contrato_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: rrhh_user
--

ALTER SEQUENCE public.anexos_extension_contrato_id_seq OWNED BY public.anexos_extension_contrato.id;


--
-- Name: bancos; Type: TABLE; Schema: public; Owner: rrhh_user
--

CREATE TABLE public.bancos (
    id integer NOT NULL,
    nombre character varying(120) NOT NULL,
    codigo_sbif character varying(10)
);


ALTER TABLE public.bancos OWNER TO rrhh_user;

--
-- Name: bancos_id_seq; Type: SEQUENCE; Schema: public; Owner: rrhh_user
--

CREATE SEQUENCE public.bancos_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.bancos_id_seq OWNER TO rrhh_user;

--
-- Name: bancos_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: rrhh_user
--

ALTER SEQUENCE public.bancos_id_seq OWNED BY public.bancos.id;


--
-- Name: cajas_compensacion; Type: TABLE; Schema: public; Owner: rrhh_user
--

CREATE TABLE public.cajas_compensacion (
    id integer NOT NULL,
    nombre character varying(150) NOT NULL
);


ALTER TABLE public.cajas_compensacion OWNER TO rrhh_user;

--
-- Name: cajas_compensacion_id_seq; Type: SEQUENCE; Schema: public; Owner: rrhh_user
--

CREATE SEQUENCE public.cajas_compensacion_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.cajas_compensacion_id_seq OWNER TO rrhh_user;

--
-- Name: cajas_compensacion_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: rrhh_user
--

ALTER SEQUENCE public.cajas_compensacion_id_seq OWNED BY public.cajas_compensacion.id;


--
-- Name: cargos; Type: TABLE; Schema: public; Owner: rrhh_user
--

CREATE TABLE public.cargos (
    id integer NOT NULL,
    nombre character varying(150) NOT NULL,
    descripcion character varying(300),
    categoria character varying(100),
    activo boolean DEFAULT true NOT NULL
);


ALTER TABLE public.cargos OWNER TO rrhh_user;

--
-- Name: cargos_id_seq; Type: SEQUENCE; Schema: public; Owner: rrhh_user
--

CREATE SEQUENCE public.cargos_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.cargos_id_seq OWNER TO rrhh_user;

--
-- Name: cargos_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: rrhh_user
--

ALTER SEQUENCE public.cargos_id_seq OWNED BY public.cargos.id;


--
-- Name: contratos; Type: TABLE; Schema: public; Owner: rrhh_user
--

CREATE TABLE public.contratos (
    id integer NOT NULL,
    trabajador_id integer NOT NULL,
    empleador_id integer,
    obra_id integer,
    cargo_id integer,
    tipo_contrato character varying(30),
    fecha_inicio date,
    fecha_termino date,
    jornada text,
    horas_semanales integer,
    sueldo_base numeric(10,2),
    asignacion_movilizacion numeric(10,2),
    asignacion_colacion numeric(10,2),
    asignacion_herramientas numeric(10,2),
    estado_contrato character varying(20) NOT NULL,
    causal_termino character varying(250),
    fecha_finiquito date,
    creado_en timestamp with time zone DEFAULT now(),
    actualizado_en timestamp with time zone,
    horario_id integer
);


ALTER TABLE public.contratos OWNER TO rrhh_user;

--
-- Name: contratos_id_seq; Type: SEQUENCE; Schema: public; Owner: rrhh_user
--

CREATE SEQUENCE public.contratos_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.contratos_id_seq OWNER TO rrhh_user;

--
-- Name: contratos_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: rrhh_user
--

ALTER SEQUENCE public.contratos_id_seq OWNED BY public.contratos.id;


--
-- Name: documentos_laborales; Type: TABLE; Schema: public; Owner: rrhh_user
--

CREATE TABLE public.documentos_laborales (
    id integer NOT NULL,
    contrato_id integer NOT NULL,
    tipo character varying(50) NOT NULL,
    nombre_archivo character varying(255) NOT NULL,
    ruta_archivo character varying(500),
    estado character varying(20) NOT NULL,
    fecha_creacion timestamp with time zone DEFAULT now()
);


ALTER TABLE public.documentos_laborales OWNER TO rrhh_user;

--
-- Name: documentos_laborales_id_seq; Type: SEQUENCE; Schema: public; Owner: rrhh_user
--

CREATE SEQUENCE public.documentos_laborales_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.documentos_laborales_id_seq OWNER TO rrhh_user;

--
-- Name: documentos_laborales_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: rrhh_user
--

ALTER SEQUENCE public.documentos_laborales_id_seq OWNED BY public.documentos_laborales.id;


--
-- Name: empleador_mutual; Type: TABLE; Schema: public; Owner: rrhh_user
--

CREATE TABLE public.empleador_mutual (
    id integer NOT NULL,
    empleador_id integer NOT NULL,
    mutual_id integer NOT NULL,
    vigente boolean NOT NULL
);


ALTER TABLE public.empleador_mutual OWNER TO rrhh_user;

--
-- Name: empleador_mutual_id_seq; Type: SEQUENCE; Schema: public; Owner: rrhh_user
--

CREATE SEQUENCE public.empleador_mutual_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.empleador_mutual_id_seq OWNER TO rrhh_user;

--
-- Name: empleador_mutual_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: rrhh_user
--

ALTER SEQUENCE public.empleador_mutual_id_seq OWNED BY public.empleador_mutual.id;


--
-- Name: empleadores; Type: TABLE; Schema: public; Owner: rrhh_user
--

CREATE TABLE public.empleadores (
    id integer NOT NULL,
    razon_social character varying(200) NOT NULL,
    rut character varying(20),
    giro character varying(200),
    direccion character varying(250),
    comuna character varying(100),
    rut_rep_legal character varying(20),
    nombre_rep_legal character varying(150)
);


ALTER TABLE public.empleadores OWNER TO rrhh_user;

--
-- Name: empleadores_id_seq; Type: SEQUENCE; Schema: public; Owner: rrhh_user
--

CREATE SEQUENCE public.empleadores_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.empleadores_id_seq OWNER TO rrhh_user;

--
-- Name: empleadores_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: rrhh_user
--

ALTER SEQUENCE public.empleadores_id_seq OWNED BY public.empleadores.id;


--
-- Name: eventos_laborales; Type: TABLE; Schema: public; Owner: rrhh_user
--

CREATE TABLE public.eventos_laborales (
    id integer NOT NULL,
    trabajador_id integer NOT NULL,
    contrato_id integer,
    obra_id integer,
    empleador_id integer,
    categoria character varying(30) NOT NULL,
    tipo character varying(60) NOT NULL,
    titulo character varying(200) NOT NULL,
    fecha_evento date NOT NULL,
    estado character varying(20) NOT NULL,
    nombre_archivo character varying(255),
    ruta_archivo character varying(500),
    metadata json,
    creado_en timestamp with time zone DEFAULT now(),
    actualizado_en timestamp with time zone
);


ALTER TABLE public.eventos_laborales OWNER TO rrhh_user;

--
-- Name: eventos_laborales_id_seq; Type: SEQUENCE; Schema: public; Owner: rrhh_user
--

CREATE SEQUENCE public.eventos_laborales_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.eventos_laborales_id_seq OWNER TO rrhh_user;

--
-- Name: eventos_laborales_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: rrhh_user
--

ALTER SEQUENCE public.eventos_laborales_id_seq OWNED BY public.eventos_laborales.id;


--
-- Name: horario_tramos; Type: TABLE; Schema: public; Owner: rrhh_user
--

CREATE TABLE public.horario_tramos (
    id integer NOT NULL,
    horario_id integer NOT NULL,
    dia_semana integer NOT NULL,
    hora_inicio time without time zone NOT NULL,
    hora_termino time without time zone NOT NULL,
    orden integer NOT NULL,
    CONSTRAINT ck_horario_tramo_dia CHECK (((dia_semana >= 0) AND (dia_semana <= 6)))
);


ALTER TABLE public.horario_tramos OWNER TO rrhh_user;

--
-- Name: horario_tramos_id_seq; Type: SEQUENCE; Schema: public; Owner: rrhh_user
--

CREATE SEQUENCE public.horario_tramos_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.horario_tramos_id_seq OWNER TO rrhh_user;

--
-- Name: horario_tramos_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: rrhh_user
--

ALTER SEQUENCE public.horario_tramos_id_seq OWNED BY public.horario_tramos.id;


--
-- Name: horarios; Type: TABLE; Schema: public; Owner: rrhh_user
--

CREATE TABLE public.horarios (
    id integer NOT NULL,
    nombre character varying(80) NOT NULL,
    descripcion text,
    activo boolean NOT NULL,
    creado_en timestamp with time zone DEFAULT now(),
    actualizado_en timestamp with time zone
);


ALTER TABLE public.horarios OWNER TO rrhh_user;

--
-- Name: horarios_id_seq; Type: SEQUENCE; Schema: public; Owner: rrhh_user
--

CREATE SEQUENCE public.horarios_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.horarios_id_seq OWNER TO rrhh_user;

--
-- Name: horarios_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: rrhh_user
--

ALTER SEQUENCE public.horarios_id_seq OWNED BY public.horarios.id;


--
-- Name: mutuales; Type: TABLE; Schema: public; Owner: rrhh_user
--

CREATE TABLE public.mutuales (
    id integer NOT NULL,
    nombre character varying(150) NOT NULL
);


ALTER TABLE public.mutuales OWNER TO rrhh_user;

--
-- Name: mutuales_id_seq; Type: SEQUENCE; Schema: public; Owner: rrhh_user
--

CREATE SEQUENCE public.mutuales_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.mutuales_id_seq OWNER TO rrhh_user;

--
-- Name: mutuales_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: rrhh_user
--

ALTER SEQUENCE public.mutuales_id_seq OWNED BY public.mutuales.id;


--
-- Name: obras; Type: TABLE; Schema: public; Owner: rrhh_user
--

CREATE TABLE public.obras (
    id integer NOT NULL,
    nombre character varying(120) NOT NULL,
    codigo character varying(50) NOT NULL,
    centro_costo character varying(100),
    comuna character varying(100),
    empleador_id integer,
    estado character varying(20) NOT NULL,
    fecha_inicio date,
    fecha_cierre date,
    direccion character varying(300)
);


ALTER TABLE public.obras OWNER TO rrhh_user;

--
-- Name: obras_id_seq; Type: SEQUENCE; Schema: public; Owner: rrhh_user
--

CREATE SEQUENCE public.obras_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.obras_id_seq OWNER TO rrhh_user;

--
-- Name: obras_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: rrhh_user
--

ALTER SEQUENCE public.obras_id_seq OWNED BY public.obras.id;


--
-- Name: roles; Type: TABLE; Schema: public; Owner: rrhh_user
--

CREATE TABLE public.roles (
    id integer NOT NULL,
    name character varying(30) NOT NULL
);


ALTER TABLE public.roles OWNER TO rrhh_user;

--
-- Name: roles_id_seq; Type: SEQUENCE; Schema: public; Owner: rrhh_user
--

CREATE SEQUENCE public.roles_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.roles_id_seq OWNER TO rrhh_user;

--
-- Name: roles_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: rrhh_user
--

ALTER SEQUENCE public.roles_id_seq OWNED BY public.roles.id;


--
-- Name: salud; Type: TABLE; Schema: public; Owner: rrhh_user
--

CREATE TABLE public.salud (
    id integer NOT NULL,
    nombre character varying(120) NOT NULL,
    tipo character varying(20) NOT NULL
);


ALTER TABLE public.salud OWNER TO rrhh_user;

--
-- Name: salud_id_seq; Type: SEQUENCE; Schema: public; Owner: rrhh_user
--

CREATE SEQUENCE public.salud_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.salud_id_seq OWNER TO rrhh_user;

--
-- Name: salud_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: rrhh_user
--

ALTER SEQUENCE public.salud_id_seq OWNED BY public.salud.id;


--
-- Name: trabajador_obras; Type: TABLE; Schema: public; Owner: rrhh_user
--

CREATE TABLE public.trabajador_obras (
    id integer NOT NULL,
    trabajador_id integer NOT NULL,
    obra_id integer NOT NULL,
    fecha_inicio date NOT NULL,
    fecha_termino date,
    vigente boolean NOT NULL,
    creado_en timestamp with time zone DEFAULT now()
);


ALTER TABLE public.trabajador_obras OWNER TO rrhh_user;

--
-- Name: trabajador_obras_id_seq; Type: SEQUENCE; Schema: public; Owner: rrhh_user
--

CREATE SEQUENCE public.trabajador_obras_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.trabajador_obras_id_seq OWNER TO rrhh_user;

--
-- Name: trabajador_obras_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: rrhh_user
--

ALTER SEQUENCE public.trabajador_obras_id_seq OWNED BY public.trabajador_obras.id;


--
-- Name: trabajadores; Type: TABLE; Schema: public; Owner: rrhh_user
--

CREATE TABLE public.trabajadores (
    id integer NOT NULL,
    rut character varying(20) NOT NULL,
    dv character varying(2),
    nombres character varying(100) NOT NULL,
    ap_paterno character varying(100) NOT NULL,
    ap_materno character varying(100) NOT NULL,
    fecha_nacimiento date,
    nacionalidad character varying(60),
    sexo character varying(10),
    estado_civil character varying(30),
    direccion character varying(250),
    comuna character varying(100),
    telefono character varying(30),
    telefono_emergencia character varying(30),
    correo character varying(150),
    banco_id integer,
    cuenta_rut character varying(20),
    cuenta_numero character varying(50),
    afp_id integer,
    salud_id integer,
    uf_plan_salud numeric(6,2),
    caja_compensacion_id integer,
    apv_activo boolean NOT NULL,
    apv_modalidad character varying(20),
    apv_valor numeric(8,2),
    apv_institucion character varying(120),
    cav_activo boolean NOT NULL,
    cav_modalidad character varying(20),
    cav_valor numeric(8,2),
    cav_institucion character varying(120),
    num_cargas_familiares integer,
    es_extranjero boolean NOT NULL,
    es_discapacitado boolean NOT NULL,
    es_pensionado boolean NOT NULL,
    tiene_examen_preocupacional boolean NOT NULL,
    fecha_examen_preocupacional date,
    tiene_curso_altura boolean NOT NULL,
    fecha_vencimiento_curso_altura date,
    tiene_induccion_obra boolean NOT NULL,
    fecha_induccion_obra date,
    obra_id integer NOT NULL,
    estado_trabajador character varying(20) NOT NULL,
    tipo_trabajador character varying(30),
    fecha_ingreso_empresa date,
    fecha_egreso_empresa date,
    creado_en timestamp with time zone DEFAULT now(),
    actualizado_en timestamp with time zone,
    cargo_id integer,
    tipo_cuenta character varying(20),
    pago_tercero_activo boolean DEFAULT false NOT NULL,
    pago_tercero_rut character varying(20),
    pago_tercero_nombre character varying(200),
    pago_tercero_banco_id integer,
    pago_tercero_tipo_cuenta character varying(20),
    pago_tercero_cuenta_numero character varying(50)
);


ALTER TABLE public.trabajadores OWNER TO rrhh_user;

--
-- Name: trabajadores_id_seq; Type: SEQUENCE; Schema: public; Owner: rrhh_user
--

CREATE SEQUENCE public.trabajadores_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.trabajadores_id_seq OWNER TO rrhh_user;

--
-- Name: trabajadores_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: rrhh_user
--

ALTER SEQUENCE public.trabajadores_id_seq OWNED BY public.trabajadores.id;


--
-- Name: user_obras; Type: TABLE; Schema: public; Owner: rrhh_user
--

CREATE TABLE public.user_obras (
    user_id integer NOT NULL,
    obra_id integer NOT NULL
);


ALTER TABLE public.user_obras OWNER TO rrhh_user;

--
-- Name: user_roles; Type: TABLE; Schema: public; Owner: rrhh_user
--

CREATE TABLE public.user_roles (
    user_id integer NOT NULL,
    role_id integer NOT NULL
);


ALTER TABLE public.user_roles OWNER TO rrhh_user;

--
-- Name: users; Type: TABLE; Schema: public; Owner: rrhh_user
--

CREATE TABLE public.users (
    id integer NOT NULL,
    username character varying(80) NOT NULL,
    email character varying(120),
    password_hash character varying(255) NOT NULL,
    is_active boolean NOT NULL,
    must_change_password boolean NOT NULL,
    created_at timestamp without time zone NOT NULL,
    last_login_at timestamp without time zone
);


ALTER TABLE public.users OWNER TO rrhh_user;

--
-- Name: users_id_seq; Type: SEQUENCE; Schema: public; Owner: rrhh_user
--

CREATE SEQUENCE public.users_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.users_id_seq OWNER TO rrhh_user;

--
-- Name: users_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: rrhh_user
--

ALTER SEQUENCE public.users_id_seq OWNED BY public.users.id;


--
-- Name: afp id; Type: DEFAULT; Schema: public; Owner: rrhh_user
--

ALTER TABLE ONLY public.afp ALTER COLUMN id SET DEFAULT nextval('public.afp_id_seq'::regclass);


--
-- Name: anexos_extension_contrato id; Type: DEFAULT; Schema: public; Owner: rrhh_user
--

ALTER TABLE ONLY public.anexos_extension_contrato ALTER COLUMN id SET DEFAULT nextval('public.anexos_extension_contrato_id_seq'::regclass);


--
-- Name: bancos id; Type: DEFAULT; Schema: public; Owner: rrhh_user
--

ALTER TABLE ONLY public.bancos ALTER COLUMN id SET DEFAULT nextval('public.bancos_id_seq'::regclass);


--
-- Name: cajas_compensacion id; Type: DEFAULT; Schema: public; Owner: rrhh_user
--

ALTER TABLE ONLY public.cajas_compensacion ALTER COLUMN id SET DEFAULT nextval('public.cajas_compensacion_id_seq'::regclass);


--
-- Name: cargos id; Type: DEFAULT; Schema: public; Owner: rrhh_user
--

ALTER TABLE ONLY public.cargos ALTER COLUMN id SET DEFAULT nextval('public.cargos_id_seq'::regclass);


--
-- Name: contratos id; Type: DEFAULT; Schema: public; Owner: rrhh_user
--

ALTER TABLE ONLY public.contratos ALTER COLUMN id SET DEFAULT nextval('public.contratos_id_seq'::regclass);


--
-- Name: documentos_laborales id; Type: DEFAULT; Schema: public; Owner: rrhh_user
--

ALTER TABLE ONLY public.documentos_laborales ALTER COLUMN id SET DEFAULT nextval('public.documentos_laborales_id_seq'::regclass);


--
-- Name: empleador_mutual id; Type: DEFAULT; Schema: public; Owner: rrhh_user
--

ALTER TABLE ONLY public.empleador_mutual ALTER COLUMN id SET DEFAULT nextval('public.empleador_mutual_id_seq'::regclass);


--
-- Name: empleadores id; Type: DEFAULT; Schema: public; Owner: rrhh_user
--

ALTER TABLE ONLY public.empleadores ALTER COLUMN id SET DEFAULT nextval('public.empleadores_id_seq'::regclass);


--
-- Name: eventos_laborales id; Type: DEFAULT; Schema: public; Owner: rrhh_user
--

ALTER TABLE ONLY public.eventos_laborales ALTER COLUMN id SET DEFAULT nextval('public.eventos_laborales_id_seq'::regclass);


--
-- Name: horario_tramos id; Type: DEFAULT; Schema: public; Owner: rrhh_user
--

ALTER TABLE ONLY public.horario_tramos ALTER COLUMN id SET DEFAULT nextval('public.horario_tramos_id_seq'::regclass);


--
-- Name: horarios id; Type: DEFAULT; Schema: public; Owner: rrhh_user
--

ALTER TABLE ONLY public.horarios ALTER COLUMN id SET DEFAULT nextval('public.horarios_id_seq'::regclass);


--
-- Name: mutuales id; Type: DEFAULT; Schema: public; Owner: rrhh_user
--

ALTER TABLE ONLY public.mutuales ALTER COLUMN id SET DEFAULT nextval('public.mutuales_id_seq'::regclass);


--
-- Name: obras id; Type: DEFAULT; Schema: public; Owner: rrhh_user
--

ALTER TABLE ONLY public.obras ALTER COLUMN id SET DEFAULT nextval('public.obras_id_seq'::regclass);


--
-- Name: roles id; Type: DEFAULT; Schema: public; Owner: rrhh_user
--

ALTER TABLE ONLY public.roles ALTER COLUMN id SET DEFAULT nextval('public.roles_id_seq'::regclass);


--
-- Name: salud id; Type: DEFAULT; Schema: public; Owner: rrhh_user
--

ALTER TABLE ONLY public.salud ALTER COLUMN id SET DEFAULT nextval('public.salud_id_seq'::regclass);


--
-- Name: trabajador_obras id; Type: DEFAULT; Schema: public; Owner: rrhh_user
--

ALTER TABLE ONLY public.trabajador_obras ALTER COLUMN id SET DEFAULT nextval('public.trabajador_obras_id_seq'::regclass);


--
-- Name: trabajadores id; Type: DEFAULT; Schema: public; Owner: rrhh_user
--

ALTER TABLE ONLY public.trabajadores ALTER COLUMN id SET DEFAULT nextval('public.trabajadores_id_seq'::regclass);


--
-- Name: users id; Type: DEFAULT; Schema: public; Owner: rrhh_user
--

ALTER TABLE ONLY public.users ALTER COLUMN id SET DEFAULT nextval('public.users_id_seq'::regclass);


--
-- Data for Name: afp; Type: TABLE DATA; Schema: public; Owner: rrhh_user
--

COPY public.afp (id, nombre) FROM stdin;
1	AFP Habitat
2	AFP Provida
3	AFP Capital
4	AFP Cuprum
5	AFP Modelo
6	AFP PlanVital
7	AFP UNO
8	IPS (Ex SSS)
\.


--
-- Data for Name: alembic_version; Type: TABLE DATA; Schema: public; Owner: rrhh_user
--

COPY public.alembic_version (version_num) FROM stdin;
e9ed466c47df
\.


--
-- Data for Name: anexos_extension_contrato; Type: TABLE DATA; Schema: public; Owner: rrhh_user
--

COPY public.anexos_extension_contrato (id, contrato_id, trabajador_id, empleador_id, obra_id, fecha_anexo, fecha_termino_anterior, fecha_termino_nueva, observaciones, formato, estado, docx_nombre, docx_ruta, pdf_nombre, pdf_ruta, creado_en, meta) FROM stdin;
\.


--
-- Data for Name: bancos; Type: TABLE DATA; Schema: public; Owner: rrhh_user
--

COPY public.bancos (id, nombre, codigo_sbif) FROM stdin;
1	Banco de Chile	1
2	Banco Santander	37
3	Banco BCI	16
4	Scotiabank	14
5	Banco Estado	12
6	Banco Itaú	39
7	Banco Security	49
9	Banco Falabella	51
10	Banco Ripley	53
11	Banco Consorcio	55
12	Banco Internacional	9
15	Corpbanca	27
16	Banco Bice	28
17	HSBC Bank	31
19	Deutsche Bank	52
20	Rabobank Chile	54
21	Banco Penta	56
22	Banco París	57
23	Banco BBVA	504
24	Coopeuch	672
25	Los Héroes	729
26	Tapp Caja Los Andes	732
27	Tenpo Prepago	730
28	Mercado Pago	875
29	Copec Pay	741
\.


--
-- Data for Name: cajas_compensacion; Type: TABLE DATA; Schema: public; Owner: rrhh_user
--

COPY public.cajas_compensacion (id, nombre) FROM stdin;
1	Caja Los Andes
2	Caja La Araucana
3	Caja Gabriela Mistral
4	Caja 18 de Septiembre
5	Caja Los Héroes
\.


--
-- Data for Name: cargos; Type: TABLE DATA; Schema: public; Owner: rrhh_user
--

COPY public.cargos (id, nombre, descripcion, categoria, activo) FROM stdin;
104	Maestro Carpintero	\N	\N	t
105	Ayudante de Carpintero	\N	\N	t
106	Maestro Carpintero Obra Gruesa	\N	\N	t
107	Ayudante Carpintero Obra Gruesa	\N	\N	t
108	Maestro Carpintero Terminaciones	\N	\N	t
109	Ayudante Carpintero Terminaciones	\N	\N	t
110	Maestro Terminaciones	\N	\N	t
111	Ayudante Terminaciones	\N	\N	t
112	Maestro Pintor	\N	\N	t
113	Ayudante de Pintor	\N	\N	t
114	Maestro Pintor - Yesero	\N	\N	t
115	Maestro Ceramista	\N	\N	t
116	Ayudante de Ceramista	\N	\N	t
117	Gásfiter	\N	\N	t
118	Ayudante de Gásfiter	\N	\N	t
119	Rondín - Día	\N	\N	t
120	Rondín - Nochero	\N	\N	t
121	Rondín Part Time - Día	\N	\N	t
122	Rondín Part Time - Noche	\N	\N	t
123	Maestro de Andamios	\N	\N	t
124	Ayudante de Andamios	\N	\N	t
125	Maestro Soldador	\N	\N	t
126	Ayudante de Soldador	\N	\N	t
127	Alumno(a) en Práctica	\N	\N	t
128	Canguero	\N	\N	t
129	Canguero - Pulidor	\N	\N	t
130	Jornalero de Obra y Mantención de Instalaciones Sanitarias	\N	\N	t
131	Llavera y encargada de aseo	\N	\N	t
132	Maestro Eléctrico	\N	\N	t
133	Maestro de Terminaciones	\N	\N	t
134	Mantención y Operador Maquinaria Pesada	\N	\N	t
135	Operador Control Interno Preventivo Diurno	\N	\N	t
136	Operador de Furgón y Ayudante Terminaciones Post Venta	\N	\N	t
137	Encargado de Mantención	\N	\N	t
138	Ayudante de Mantención	\N	\N	t
139	Operador Maquinaria Pesada	\N	\N	t
140	Maestro Andamiero	\N	\N	t
141	Ayudante de Andamiero	\N	\N	t
142	Maestro Concretero	\N	\N	t
143	Jornalero de montaje	\N	\N	t
144	Portería de Obra	\N	\N	t
145	Jornalero de Obra y Bodega	\N	\N	t
146	Asistente Depto. Administración y Prevención	\N	\N	t
147	Encargada de llaves	\N	\N	t
148	Ayudante de trazador	\N	\N	t
149	Trazador	\N	\N	t
150	Encargada de limpieza	\N	\N	t
151	Nivelador	\N	\N	t
152	Jornal Concretero	\N	\N	t
153	Maestro Enfierrador	\N	\N	t
154	Encargada de aseo	\N	\N	t
155	Ayudante de Eléctrico	\N	\N	t
156	Maestro Carpintero Terminaciones P.V.	\N	\N	t
157	Rigger	\N	\N	t
158	Operador Pluma Torre	\N	\N	t
159	Pulidor	\N	\N	t
160	Ayudante de Terminaciones y Aseo P.V.	\N	\N	t
161	Operador Control Interno Preventivo Nocturno	\N	\N	t
162	Operador Control Interno Preventivo Diurno - Part Time	\N	\N	t
163	Operador Control Interno Preventivo Nocturno - Part Time	\N	\N	t
164	Maestro Carpintero 2da Terminaciones	\N	\N	t
165	Maestro Carpintero 2da Obra Gruesa	\N	\N	t
201	Administrador de Obra	\N	\N	t
202	Jefe de Obra	\N	\N	t
203	Jefe Oficina Técnica	\N	\N	t
204	Ayudante Oficina Técnica	\N	\N	t
205	Administrativo de Obra	\N	\N	t
206	Ayudante Administrativo	\N	\N	t
207	Prevencionista de Riesgos	\N	\N	t
208	Ayudante de Prevención de Riesgos	\N	\N	t
209	Asistente de Obra	\N	\N	t
210	Supervisor de Obra	\N	\N	t
211	Supervisor de Hormigones	\N	\N	t
212	Supervisor de Andamios	\N	\N	t
213	Control de Calidad	\N	\N	t
214	Operador Camión Pluma	\N	\N	t
215	Encargado de Bodega	\N	\N	t
216	Ayudante de Bodega	\N	\N	t
217	Encargada de compras	\N	\N	t
218	Jefe de Terreno	\N	\N	t
219	Supervisor de Urbanización	\N	\N	t
220	Jefe de Bodega	\N	\N	t
221	Encargado Oficina Técnica	\N	\N	t
222	Operador Retro Excavadora	\N	\N	t
223	Operador Camión Tolva	\N	\N	t
224	Capataz de Andamios	\N	\N	t
225	Técnico Topográfico	\N	\N	t
226	Capataz de Obra	\N	\N	t
227	Chofer de camión y Operador de maquinaria pesada	\N	\N	t
228	Jefe de seguridad	\N	\N	t
229	Ayudante de Oficina Técnica y Calidad	\N	\N	t
230	Practicante - Ingeniería en Construcción	\N	\N	t
301	Gerente General	\N	\N	t
302	Gerente de Procesos	\N	\N	t
303	Jefe Departamento Administrativo	\N	\N	t
304	Jefe Recursos Humanos	\N	\N	t
305	Jefe Departamento de Prevención de Riesgos	\N	\N	t
306	Encargado de Bodegas y Pago a Proveedores	\N	\N	t
307	Jefe Departamento Post Venta	\N	\N	t
101	Jornalero de Obra	None	Obra	t
102	Maestro Albañil	None	Obra	t
103	Ayudante de Albañil	None	Obra	t
\.


--
-- Data for Name: contratos; Type: TABLE DATA; Schema: public; Owner: rrhh_user
--

COPY public.contratos (id, trabajador_id, empleador_id, obra_id, cargo_id, tipo_contrato, fecha_inicio, fecha_termino, jornada, horas_semanales, sueldo_base, asignacion_movilizacion, asignacion_colacion, asignacion_herramientas, estado_contrato, causal_termino, fecha_finiquito, creado_en, actualizado_en, horario_id) FROM stdin;
1	2	2	9	160	PLAZO_FIJO	2025-08-18	2025-09-30	Horario normal	44	550000.00	0.00	0.00	0.00	VIGENTE	\N	\N	2026-01-07 01:42:33.801247+00	\N	\N
2	3	2	9	156	PLAZO_FIJO	2025-05-01	2025-07-31	Horario normal	44	650000.00	0.00	0.00	0.00	VIGENTE	\N	\N	2026-01-07 01:46:40.064142+00	\N	\N
3	4	2	9	156	PLAZO_FIJO	2025-05-01	2025-07-31	Horario normal	44	850000.00	0.00	0.00	0.00	VIGENTE	\N	\N	2026-01-07 02:06:57.257621+00	\N	\N
5	1	2	11	306	INDEFINIDO	2022-11-01	2025-07-31	Horario normal	44	950000.00	30000.00	30000.00	\N	VIGENTE	\N	\N	2026-01-07 02:16:44.441728+00	2026-01-07 02:23:20.8344+00	\N
6	6	2	9	156	PLAZO_FIJO	2025-04-01	2025-05-31	Horario normal	44	850000.00	10000.00	10000.00	\N	VIGENTE	\N	\N	2026-01-07 04:03:22.797893+00	\N	\N
7	7	2	9	156	PLAZO_FIJO	2025-05-01	2025-07-31	Horario normal	44	540000.00	0.00	0.00	0.00	VIGENTE	\N	\N	2026-01-07 04:06:19.534075+00	\N	\N
8	8	2	9	307	PLAZO_FIJO	2025-05-01	2025-07-31	Horario normal	44	1600000.00	80000.00	80000.00	0.00	VIGENTE	\N	\N	2026-01-07 18:02:36.336194+00	\N	\N
10	10	1	3	143	PLAZO_FIJO	2026-01-06	2026-01-31	\N	44	529000.00	\N	\N	\N	VIGENTE	\N	\N	2026-01-07 21:29:26.662842+00	2026-01-07 23:05:33.109364+00	2
9	9	1	1	105	PLAZO_FIJO	2026-01-05	2026-01-31	\N	44	570000.00	\N	\N	\N	VIGENTE	\N	\N	2026-01-07 20:57:01.552054+00	2026-01-07 23:10:27.660059+00	2
14	15	1	1	143	PLAZO_FIJO	2026-01-06	2026-01-31	\N	44	529000.00	\N	\N	\N	VIGENTE	\N	\N	2026-01-07 22:18:25.539765+00	2026-01-07 23:16:48.218587+00	2
15	16	1	1	143	PLAZO_FIJO	2026-01-06	2026-01-31	\N	44	529000.00	\N	\N	\N	VIGENTE	\N	\N	2026-01-07 22:21:46.638192+00	2026-01-07 23:18:18.853158+00	2
11	11	1	1	143	PLAZO_FIJO	2026-01-06	2026-01-31	\N	44	529000.00	\N	\N	\N	VIGENTE	\N	\N	2026-01-07 21:33:42.09323+00	2026-01-07 23:27:39.449017+00	2
16	17	1	1	101	PLAZO_FIJO	2026-01-06	2026-01-31	\N	44	529000.00	\N	\N	\N	VIGENTE	\N	\N	2026-01-07 22:25:20.539789+00	2026-01-07 23:30:49.676846+00	2
4	5	2	9	156	PLAZO_FIJO	2025-05-01	2025-07-31	\N	44	700000.00	\N	\N	\N	VIGENTE	\N	\N	2026-01-07 02:10:17.329565+00	2026-01-08 00:05:08.461358+00	2
12	13	1	1	106	PLAZO_FIJO	2026-01-06	2026-01-31	\N	44	600000.00	\N	\N	\N	VIGENTE	\N	\N	2026-01-07 21:57:20.501817+00	2026-01-09 00:30:53.273858+00	2
17	18	2	11	106	PLAZO_FIJO	2026-01-06	2026-01-31	Lunes a jueves, de 08:00 hrs. a 13:00 hrs., y de 14:00 hrs. a 18:00 hrs. Viernes, de 08:00 hrs. a 13:00 hrs. y de 14:00 hrs. a 17:00 hrs.	44	600000.00	0.00	0.00	0.00	VIGENTE	\N	\N	2026-01-09 01:49:48.569331+00	\N	2
13	14	1	1	105	PLAZO_FIJO	2026-01-06	2026-01-31	\N	44	529000.00	\N	\N	\N	VIGENTE	\N	\N	2026-01-07 22:02:51.745149+00	2026-01-09 04:59:52.40036+00	2
18	19	1	1	149	PLAZO_FIJO	2025-12-01	2025-12-31	Lunes a jueves, de 08:00 hrs. a 13:00 hrs., y de 14:00 hrs. a 18:00 hrs. Viernes, de 08:00 hrs. a 13:00 hrs. y de 14:00 hrs. a 17:00 hrs.	44	850000.00	\N	\N	\N	VIGENTE	\N	\N	2026-01-09 18:09:26.073797+00	2026-01-09 18:23:35.308668+00	2
\.


--
-- Data for Name: documentos_laborales; Type: TABLE DATA; Schema: public; Owner: rrhh_user
--

COPY public.documentos_laborales (id, contrato_id, tipo, nombre_archivo, ruta_archivo, estado, fecha_creacion) FROM stdin;
\.


--
-- Data for Name: empleador_mutual; Type: TABLE DATA; Schema: public; Owner: rrhh_user
--

COPY public.empleador_mutual (id, empleador_id, mutual_id, vigente) FROM stdin;
\.


--
-- Data for Name: empleadores; Type: TABLE DATA; Schema: public; Owner: rrhh_user
--

COPY public.empleadores (id, razon_social, rut, giro, direccion, comuna, rut_rep_legal, nombre_rep_legal) FROM stdin;
1	Constructora Valencia SpA	76.772.137-4	Construcción de Edificios para uso residencial	Los Alelíes Nro. 19, Pobl. Don Sergio	Puchuncaví	8.116.857-1	Alejandro de Caso Rodríguez
2	Constructora Salem SpA	76.969.607-5	Construcción de Edificios para uso residencial	Los Alelíes Nro. 19, Pobl. Don Sergio	Puchuncaví	8.116.857-1	Alejandro de Caso Rodríguez
3	Transportes Terratrán SpA	76.094.597-8	Arriendo de maquinarias y equipos	Los Alelíes Nro. 19, Pobl. Don Sergio	Puchuncaví	8.116.857-1	Alejandro de Caso Rodríguez
4	Proveedora de Servicios Caronte SpA	76.829.034-2	Proveedora de RRHH	Serrano Nro. 1000	Quilpué	16.232.010-6	Armando Andrés Ortiz Espinoza
5	Proveedora de Servicios FMO SpA	76.829.036-9	Proveedora de RRHH	Los Alelíes Nro. 19, Pobl. Don Sergio	Puchuncaví	9.707.322-8	Héctor Fernando Moya Roco
\.


--
-- Data for Name: eventos_laborales; Type: TABLE DATA; Schema: public; Owner: rrhh_user
--

COPY public.eventos_laborales (id, trabajador_id, contrato_id, obra_id, empleador_id, categoria, tipo, titulo, fecha_evento, estado, nombre_archivo, ruta_archivo, metadata, creado_en, actualizado_en) FROM stdin;
\.


--
-- Data for Name: horario_tramos; Type: TABLE DATA; Schema: public; Owner: rrhh_user
--

COPY public.horario_tramos (id, horario_id, dia_semana, hora_inicio, hora_termino, orden) FROM stdin;
1	4	0	00:00:00	06:00:00	1
2	4	5	20:00:00	23:59:00	1
3	4	6	00:00:00	06:00:00	1
4	4	6	20:00:00	23:59:00	2
5	2	0	08:00:00	13:00:00	1
6	2	0	14:00:00	18:00:00	2
7	2	1	08:00:00	13:00:00	1
8	2	1	14:00:00	18:00:00	2
9	2	2	08:00:00	13:00:00	1
10	2	2	14:00:00	18:00:00	2
11	2	3	08:00:00	13:00:00	1
12	2	3	14:00:00	18:00:00	2
13	2	4	08:00:00	13:00:00	1
14	2	4	14:00:00	17:00:00	2
15	3	0	20:00:00	23:59:00	1
16	3	1	00:00:00	06:00:00	1
17	3	1	20:00:00	23:59:00	2
18	3	2	00:00:00	06:00:00	1
19	3	2	20:00:00	23:59:00	2
20	3	3	00:00:00	06:00:00	1
21	3	3	20:00:00	23:59:00	2
22	3	4	00:00:00	06:00:00	1
23	3	4	20:00:00	23:59:00	2
24	3	5	00:00:00	05:00:00	1
25	5	5	08:00:00	18:00:00	1
26	5	6	08:00:00	18:00:00	1
\.


--
-- Data for Name: horarios; Type: TABLE DATA; Schema: public; Owner: rrhh_user
--

COPY public.horarios (id, nombre, descripcion, activo, creado_en, actualizado_en) FROM stdin;
2	Horario Normal (L-J 08-13/14-18; V 08-13/14-17)	Lunes a jueves, de 08:00 hrs. a 13:00 hrs., y de 14:00 hrs. a 18:00 hrs. Viernes, de 08:00 hrs. a 13:00 hrs. y de 14:00 hrs. a 17:00 hrs.	t	2026-01-07 22:31:16.796744+00	\N
4	Guardia Nocturno Part Time	Sábado, desde las 20:00 horas hasta las 06:00 horas del día domingo, con una hora destinada a colación. Domingo, desde las 20:00 horas hasta las 06:00 horas del día lunes, con una hora destinada a colación.	t	2026-01-07 23:57:26.922204+00	\N
1	Normal	Lunes a Jueves, de 08:00 hrs. a 13:00 hrs., y de 14:00 hrs. a 18:00 hrs. Viernes, de 08:00 hrs. a 13:00 hrs., y de 14:00 hrs. a 17:00 hrs.	f	2026-01-07 21:26:39.683881+00	2026-01-07 23:59:34.186277+00
3	Guardia Nocturno Jornada Completa	Lunes a jueves, de 20:00 hrs. a 00:00 hrs., y de 01:00 hrs. a 06:00 hrs. Viernes, de 20:00 hrs. a 00:00 hrs. y Sábado de 01:00 hrs. a 05:00 hrs.	t	2026-01-07 22:31:16.796744+00	2026-01-08 00:02:54.886673+00
5	Guardia Diurno Part Time	Sábado a Domingo, de 08:00 hrs a 18:00 hrs., con 1 hora destinada a colación	t	2026-01-08 00:04:20.085298+00	\N
\.


--
-- Data for Name: mutuales; Type: TABLE DATA; Schema: public; Owner: rrhh_user
--

COPY public.mutuales (id, nombre) FROM stdin;
\.


--
-- Data for Name: obras; Type: TABLE DATA; Schema: public; Owner: rrhh_user
--

COPY public.obras (id, nombre, codigo, centro_costo, comuna, empleador_id, estado, fecha_inicio, fecha_cierre, direccion) FROM stdin;
1	Construyendo Nuestro Sueño	108	QUINTERO	Quintero	\N	ACTIVA	\N	\N	Calle Valdivia Nro. 3055
2	Condominio Isidora Goyenechea	105	QUINTERO	Quintero	\N	ACTIVA	\N	\N	Calle Salas esq. Valdivia, S/N
4	Condominio Francisco Coloane II	107	QUINTERO	Quintero	\N	ACTIVA	\N	\N	Calle Portales Nro. 3038
3	Condominio Francisco Coloane I	106	QUINTERO	Quintero	\N	ACTIVA	\N	\N	Calle Valdivia Nro. 2947
6	Bellavista	101	BELLAVISTA	Viña del Mar	\N	ACTIVA	\N	\N	Bellavista Nro. 1045, Reñaca
7	Don Francisco	102	DON FRANCISCO	Quillota	\N	ACTIVA	\N	\N	Aníbal Pinto Nro. 1040
8	Doña Josefina	103	DOÑA JOSEFINA	La Cruz	\N	ACTIVA	\N	\N	Camino Troncal Nro. 7690, Lote 6
9	Post Venta	104	POST VENTA	Villa Alemana	\N	ACTIVA	\N	\N	Avenida Valparaíso Nro. 1020
10	Condominio Vicente Huidobro	109	VICENTE HUIDOBRO	Cartagena	\N	ACTIVA	\N	\N	Camino Viejo a San Antonio Nro. 751, Lote A-2
11	Locales Comerciales	110	LOCALES COMERCIALES	Villa Alemana	\N	ACTIVA	\N	\N	Avenida Valparaíso Nro. 1020
\.


--
-- Data for Name: roles; Type: TABLE DATA; Schema: public; Owner: rrhh_user
--

COPY public.roles (id, name) FROM stdin;
1	ADMIN
2	OPERADOR
3	REVISOR
\.


--
-- Data for Name: salud; Type: TABLE DATA; Schema: public; Owner: rrhh_user
--

COPY public.salud (id, nombre, tipo) FROM stdin;
1	FONASA	FONASA
2	Colmena	ISAPRE
3	Consalud	ISAPRE
4	Cruz Blanca	ISAPRE
5	Nueva Masvida	ISAPRE
6	Banmédica	ISAPRE
7	Vida Tres	ISAPRE
\.


--
-- Data for Name: trabajador_obras; Type: TABLE DATA; Schema: public; Owner: rrhh_user
--

COPY public.trabajador_obras (id, trabajador_id, obra_id, fecha_inicio, fecha_termino, vigente, creado_en) FROM stdin;
\.


--
-- Data for Name: trabajadores; Type: TABLE DATA; Schema: public; Owner: rrhh_user
--

COPY public.trabajadores (id, rut, dv, nombres, ap_paterno, ap_materno, fecha_nacimiento, nacionalidad, sexo, estado_civil, direccion, comuna, telefono, telefono_emergencia, correo, banco_id, cuenta_rut, cuenta_numero, afp_id, salud_id, uf_plan_salud, caja_compensacion_id, apv_activo, apv_modalidad, apv_valor, apv_institucion, cav_activo, cav_modalidad, cav_valor, cav_institucion, num_cargas_familiares, es_extranjero, es_discapacitado, es_pensionado, tiene_examen_preocupacional, fecha_examen_preocupacional, tiene_curso_altura, fecha_vencimiento_curso_altura, tiene_induccion_obra, fecha_induccion_obra, obra_id, estado_trabajador, tipo_trabajador, fecha_ingreso_empresa, fecha_egreso_empresa, creado_en, actualizado_en, cargo_id, tipo_cuenta, pago_tercero_activo, pago_tercero_rut, pago_tercero_nombre, pago_tercero_banco_id, pago_tercero_tipo_cuenta, pago_tercero_cuenta_numero) FROM stdin;
10	26009572	2	Gary	Alcime	-	1987-06-18	Haitiana	M	CASADO	Gómez Carreño Nro. 2942	Quintero	+56 9 4980 1248	Nervil / +56 9 4043 9762	garryalcime79@gmail.com	5	26009572	26009572	6	1	\N	\N	f	\N	\N	\N	f	\N	\N	\N	\N	f	f	f	f	\N	f	\N	f	\N	3	VIGENTE	DIRECTO	2026-01-06	\N	2026-01-07 21:11:14.225238+00	2026-01-09 16:09:14.562443+00	143	CTA_RUT	f	\N	\N	\N	\N	\N
3	13.189.919-K	\N	Cristian Ulises	Carvajal	Guerra	1977-04-08	Chilena	M	SOLTERO	Villa Cuming, Block N° 873, Depto. N° 13	Quilpué	+56 9 6670 2384	\N	cristiancarvajal1220@gmail.com	5	1318991	1318991	1	1	\N	\N	f	\N	\N	\N	f	\N	\N	\N	\N	f	f	f	f	\N	f	\N	f	\N	9	VIGENTE	\N	2025-05-01	\N	2026-01-07 01:45:04.365733+00	2026-01-07 01:45:30.923907+00	156	CTA_RUT	f	\N	\N	\N	\N	\N
2	16.540.714-8	\N	Elizabeth Constanza	Brown	Corazanis	1987-07-25	Chilena	F	SOLTERO	Avenida Condell Nro. 786, Dpto. GP4	Quillota	+56 9 6354 6925	\N	elizabethbrowncorazanis@gmail.com	5	16540714	16540714	2	1	\N	1	f	\N	\N	\N	f	\N	\N	\N	\N	f	f	f	f	\N	f	\N	f	\N	9	VIGENTE	DIRECTO	2025-08-18	\N	2026-01-07 01:33:55.849669+00	2026-01-07 01:45:51.484766+00	160	CTA_RUT	f	\N	\N	\N	\N	\N
4	11.832.022-0	\N	Juan Carlos	Gutiérrez	Campos	1970-04-05	Chilena	M	CASADO	Tocopilla N° 01663, Pompeya Norte	Quilpué	+56 9 6637 4841	\N	juancamello1970@gmail.com	5	11832022	11832022	2	1	\N	1	f	\N	\N	\N	f	\N	\N	\N	\N	f	f	f	f	\N	f	\N	f	\N	9	VIGENTE	DIRECTO	2025-05-01	\N	2026-01-07 02:06:20.351625+00	\N	156	CTA_RUT	f	\N	\N	\N	\N	\N
5	11.223.025-4	\N	Alex Enrique	Ovalle	Bernal	1968-05-04	Chilena	M	CASADO	Luis Orione N° 1010	Quintero	+56 9 6592 2917	\N	ovalle11alex@gmail.com	9	\N	14510208391	2	1	\N	1	f	\N	\N	\N	f	\N	\N	\N	\N	f	f	f	f	\N	f	\N	f	\N	9	VIGENTE	DIRECTO	2025-05-01	\N	2026-01-07 02:09:24.456718+00	\N	156	CORRIENTE	f	\N	\N	\N	\N	\N
1	7.241.970-7	\N	Luis Eduardo	Abarca	Mayea	1957-12-20	Chilena	M	CASADO	Juan José Latorre N° 1076, Retiro	Quilpué	+56982352881	\N	abarcamayea.luis@yahoo.es	2	\N	1713386576	1	1	\N	1	t	PORCENTAJE	\N	Habitat	f	\N	\N	\N	0	f	f	f	f	\N	f	\N	f	\N	11	VIGENTE	DIRECTO	2022-11-01	\N	2026-01-06 22:17:08.510003+00	2026-01-07 02:23:20.8344+00	306	VISTA	f	\N	\N	\N	\N	\N
6	8.251.469-4	\N	Mario Armando	Pacheco	León	1960-09-10	Chilena	M	CASADO	Checoslovaquia N° 658 Villa Hermosa	Viña del Mar	+56 9 8601 2179	Margarita / +56 9 8607 2161	pachecoleonmario68@gmail.com	5	8251469	8251469	2	1	\N	1	f	\N	\N	\N	f	\N	\N	\N	\N	f	f	f	f	\N	f	\N	f	\N	9	VIGENTE	DIRECTO	2025-04-01	\N	2026-01-07 04:02:39.499065+00	\N	156	CTA_RUT	f	\N	\N	\N	\N	\N
7	8.156.622-4	\N	Óscar Benigno	Puebla	Ponce	1959-12-31	Chilena	M	CASADO	Calle Uno Nro. 2634	Quintero	+56 9 9303 6311	Margarita / +56 9 6330 2993	pueblaoscar135@gmail.com	5	8156622	8156622	1	1	\N	1	f	\N	\N	\N	f	\N	\N	\N	\N	f	f	f	f	\N	f	\N	f	\N	9	VIGENTE	DIRECTO	2025-05-01	\N	2026-01-07 04:05:48.634453+00	\N	156	CTA_RUT	f	\N	\N	\N	\N	\N
8	18.299.146-5	\N	Byron Isaac	Suárez	Salazar	1993-01-07	Chilena	M	CASADO	Camino Los Ingleses Nro. 715, Depto. 1704, Cerro Las Delicias	Valparaíso	+56 9 4290 4920	+56 32 223 1792	b.isuarezs93@gmail.com	1	\N	1013274309	6	2	\N	1	f	\N	\N	\N	f	\N	\N	\N	\N	f	f	f	f	\N	f	\N	f	\N	9	VIGENTE	DIRECTO	2025-05-01	\N	2026-01-07 18:01:41.99144+00	\N	307	CORRIENTE	f	\N	\N	\N	\N	\N
9	13306657-8	\N	Eric Fernando	Zamorano	Saure	1976-12-29	Chilena	M	CASADO	Calle Esperanza Nro. 33, Pobl. Manuel Bustos	Viña del Mar	+56 9 7777 2347	Nicol / +56 9 2816 7524	ericzamorano1976@gmail.com	5	13306657	13306657	2	1	\N	\N	f	\N	\N	\N	f	\N	\N	\N	\N	f	f	f	f	\N	f	\N	f	\N	1	VIGENTE	DIRECTO	2026-01-05	\N	2026-01-07 20:46:16.793494+00	\N	105	CTA_RUT	f	\N	\N	\N	\N	\N
13	17982882-0	\N	Rudy Jonathan	Lagos	Soto	1991-10-16	Chilena	M	SOLTERO	Avda. Argentina Nro. 912	Quintero	+56 9 5168 4234	Solange / +56 9 9235 9209	jonaaat.lag.so@gmail.com	5	17982882	17982882	2	1	\N	\N	f	\N	\N	\N	f	\N	\N	\N	\N	f	f	f	f	\N	f	\N	f	\N	1	VIGENTE	DIRECTO	2026-01-06	\N	2026-01-07 21:56:42.614081+00	\N	106	CTA_RUT	f	\N	\N	\N	\N	\N
14	19153900-1	\N	Marcelo Alejandro	Muñoz	Cáceres	1996-05-25	Chilena	M	SOLTERO	Pasaje Santa Ema Nro. 706, Nueva Aurora	Viña del Mar	+56 9 3612 9290	Mauricio / +56 9 7354 8251	chelodeejay@gmail.com	5	19153900	19153900	5	1	\N	\N	f	\N	\N	\N	f	\N	\N	\N	\N	f	f	f	f	\N	f	\N	f	\N	1	VIGENTE	DIRECTO	2026-01-06	\N	2026-01-07 22:02:24.527442+00	\N	105	CTA_RUT	f	\N	\N	\N	\N	\N
15	19918923-9	\N	Franco Silvano	Oyarce	Franco	1998-10-12	Chilena	M	SOLTERO	Villa Quinta Normal Nro. 3228, Loncura	Quintero	+56 9 3325 1640	Eliana / +56 9 5523 5742	francosantino.343@gmail.com	5	19918923	19918923	6	1	\N	\N	f	\N	\N	\N	f	\N	\N	\N	\N	f	f	f	f	\N	f	\N	f	\N	1	VIGENTE	DIRECTO	2026-01-06	\N	2026-01-07 22:17:50.687231+00	\N	143	CTA_RUT	f	\N	\N	\N	\N	\N
16	18292893-3	\N	Arturo Alexander	Santa María	Muñoz	1992-06-09	Chilena	M	SOLTERO	Independencia, Sitio 9, Centinela	Quintero	+56 9 5792 1085	Maritza / +56 9 5083 3686	arturoalexander.santamaria@gmail.com	5	18292893	18292893	1	1	\N	\N	f	\N	\N	\N	f	\N	\N	\N	\N	f	f	f	f	\N	f	\N	f	\N	1	VIGENTE	DIRECTO	2026-01-06	\N	2026-01-07 22:21:19.099393+00	\N	143	CTA_RUT	f	\N	\N	\N	\N	\N
17	17636423-8	\N	Cristian Alejandro	Pacheco	Pacheco	1990-05-10	Chilena	M	CASADO	Yungay Nro. 3455, Villa Santa Victoria	Quintero	+56 9 4779 1306	Rosa / +56 9 5855 3508	cristianpacheco55@gmail.com	5	17636423	17636423	6	1	\N	\N	f	\N	\N	\N	f	\N	\N	\N	\N	f	f	f	f	\N	f	\N	f	\N	1	VIGENTE	DIRECTO	2026-01-06	\N	2026-01-07 22:24:54.369258+00	2026-01-07 22:25:36.990178+00	101	CTA_RUT	f	\N	\N	\N	\N	\N
18	10595384-4	\N	Gustavo Aquiles	Campos	Erices	1966-05-12	Chilena	M	CASADO	Balmaceda Nro. 61, Paradero 8	Villa Alemana	+56 9 9326 9117	\N	cgustavoaquiles@gmail.com	5	10595384	10595384	2	1	\N	\N	f	\N	\N	\N	f	\N	\N	\N	\N	f	f	f	f	\N	f	\N	f	\N	11	VIGENTE	DIRECTO	2026-01-06	\N	2026-01-09 01:49:05.721901+00	\N	106	CTA_RUT	f	\N	\N	\N	\N	\N
11	8042331	4	Jorge Luis	Díaz	López	1960-01-26	Chilena	M	CASADO	Salas esq. Isidora Goyenechea, Sitio 7	Quintero	+56 9 9350 6629	Alejandra / +56 9 5355 3763	jorge.diaz.lopez60@gmail.com	5	8042331	8042331	2	1	\N	\N	f	\N	\N	\N	f	\N	\N	\N	\N	f	f	f	f	\N	f	\N	f	\N	1	VIGENTE	DIRECTO	2026-01-06	\N	2026-01-07 21:32:03.428168+00	2026-01-09 15:00:20.307004+00	143	CTA_RUT	f	\N	\N	\N	\N	\N
19	17480310	2	Cristian Andrés	Arancibia	Guzmán	1990-06-04	Chilena	M	SOLTERO	Calle Trece Nro. 317, Paradero 11½, Reñaca Alto	Viña del Mar	+56 9 5189 8070	Evelyn / +56 9 9689 1657	cristianarancibia7715@gmail.com	5	17480310	17480310	2	1	\N	\N	f	\N	\N	\N	f	\N	\N	\N	\N	f	f	f	f	\N	f	\N	f	\N	1	VIGENTE	DIRECTO	2025-12-01	\N	2026-01-09 18:08:57.028154+00	\N	149	CTA_RUT	f	\N	\N	\N	\N	\N
\.


--
-- Data for Name: user_obras; Type: TABLE DATA; Schema: public; Owner: rrhh_user
--

COPY public.user_obras (user_id, obra_id) FROM stdin;
2	1
2	2
2	4
2	3
2	6
2	7
2	8
2	9
2	10
2	11
\.


--
-- Data for Name: user_roles; Type: TABLE DATA; Schema: public; Owner: rrhh_user
--

COPY public.user_roles (user_id, role_id) FROM stdin;
1	1
2	2
3	1
\.


--
-- Data for Name: users; Type: TABLE DATA; Schema: public; Owner: rrhh_user
--

COPY public.users (id, username, email, password_hash, is_active, must_change_password, created_at, last_login_at) FROM stdin;
2	mortiz	mortiz@grupo-cs.cl	scrypt:32768:8:1$DN1y2wsiR2re3tUy$b1b545ec6344be63f5689f0eed3c611355ac7d50a1347453995540753bb4344e3952b22d4b6d5c417e52e02ca9f1340be53cd9da8cfd4d2d6f607ecaf08dd299	t	f	2026-01-06 21:39:21.446336	\N
1	admin	\N	scrypt:32768:8:1$IJLZZ5Vg2AiFl5w3$a38972c61aa502216fbf2dd6b72fec73c23b86051059ab935f5d85bebd8242d6f460a297cea37a707fb10ff88581b41066d2a4ab517dc2ac2f729ed65e6fbc87	t	f	2026-01-06 20:44:20.514519	2026-01-06 22:07:04.608869
3	aortiz	aortiz@grupo-cs.cl	scrypt:32768:8:1$BDhaHLGqs2RhwDtR$976a456bfa4569606399a94999f508f04815870284498d636961d15d1cb9dbd71d65b7177ec87e989b462198106d2ddb4b7f52617e475cc7420f900572655f5d	t	f	2026-01-06 22:07:38.728216	2026-01-07 08:31:02.09542
\.


--
-- Name: afp_id_seq; Type: SEQUENCE SET; Schema: public; Owner: rrhh_user
--

SELECT pg_catalog.setval('public.afp_id_seq', 8, true);


--
-- Name: anexos_extension_contrato_id_seq; Type: SEQUENCE SET; Schema: public; Owner: rrhh_user
--

SELECT pg_catalog.setval('public.anexos_extension_contrato_id_seq', 1, false);


--
-- Name: bancos_id_seq; Type: SEQUENCE SET; Schema: public; Owner: rrhh_user
--

SELECT pg_catalog.setval('public.bancos_id_seq', 29, true);


--
-- Name: cajas_compensacion_id_seq; Type: SEQUENCE SET; Schema: public; Owner: rrhh_user
--

SELECT pg_catalog.setval('public.cajas_compensacion_id_seq', 5, true);


--
-- Name: cargos_id_seq; Type: SEQUENCE SET; Schema: public; Owner: rrhh_user
--

SELECT pg_catalog.setval('public.cargos_id_seq', 1, false);


--
-- Name: contratos_id_seq; Type: SEQUENCE SET; Schema: public; Owner: rrhh_user
--

SELECT pg_catalog.setval('public.contratos_id_seq', 18, true);


--
-- Name: documentos_laborales_id_seq; Type: SEQUENCE SET; Schema: public; Owner: rrhh_user
--

SELECT pg_catalog.setval('public.documentos_laborales_id_seq', 1, false);


--
-- Name: empleador_mutual_id_seq; Type: SEQUENCE SET; Schema: public; Owner: rrhh_user
--

SELECT pg_catalog.setval('public.empleador_mutual_id_seq', 1, false);


--
-- Name: empleadores_id_seq; Type: SEQUENCE SET; Schema: public; Owner: rrhh_user
--

SELECT pg_catalog.setval('public.empleadores_id_seq', 1, false);


--
-- Name: eventos_laborales_id_seq; Type: SEQUENCE SET; Schema: public; Owner: rrhh_user
--

SELECT pg_catalog.setval('public.eventos_laborales_id_seq', 1, false);


--
-- Name: horario_tramos_id_seq; Type: SEQUENCE SET; Schema: public; Owner: rrhh_user
--

SELECT pg_catalog.setval('public.horario_tramos_id_seq', 26, true);


--
-- Name: horarios_id_seq; Type: SEQUENCE SET; Schema: public; Owner: rrhh_user
--

SELECT pg_catalog.setval('public.horarios_id_seq', 5, true);


--
-- Name: mutuales_id_seq; Type: SEQUENCE SET; Schema: public; Owner: rrhh_user
--

SELECT pg_catalog.setval('public.mutuales_id_seq', 1, false);


--
-- Name: obras_id_seq; Type: SEQUENCE SET; Schema: public; Owner: rrhh_user
--

SELECT pg_catalog.setval('public.obras_id_seq', 11, true);


--
-- Name: roles_id_seq; Type: SEQUENCE SET; Schema: public; Owner: rrhh_user
--

SELECT pg_catalog.setval('public.roles_id_seq', 3, true);


--
-- Name: salud_id_seq; Type: SEQUENCE SET; Schema: public; Owner: rrhh_user
--

SELECT pg_catalog.setval('public.salud_id_seq', 7, true);


--
-- Name: trabajador_obras_id_seq; Type: SEQUENCE SET; Schema: public; Owner: rrhh_user
--

SELECT pg_catalog.setval('public.trabajador_obras_id_seq', 1, false);


--
-- Name: trabajadores_id_seq; Type: SEQUENCE SET; Schema: public; Owner: rrhh_user
--

SELECT pg_catalog.setval('public.trabajadores_id_seq', 19, true);


--
-- Name: users_id_seq; Type: SEQUENCE SET; Schema: public; Owner: rrhh_user
--

SELECT pg_catalog.setval('public.users_id_seq', 3, true);


--
-- Name: afp afp_nombre_key; Type: CONSTRAINT; Schema: public; Owner: rrhh_user
--

ALTER TABLE ONLY public.afp
    ADD CONSTRAINT afp_nombre_key UNIQUE (nombre);


--
-- Name: afp afp_pkey; Type: CONSTRAINT; Schema: public; Owner: rrhh_user
--

ALTER TABLE ONLY public.afp
    ADD CONSTRAINT afp_pkey PRIMARY KEY (id);


--
-- Name: alembic_version alembic_version_pkc; Type: CONSTRAINT; Schema: public; Owner: rrhh_user
--

ALTER TABLE ONLY public.alembic_version
    ADD CONSTRAINT alembic_version_pkc PRIMARY KEY (version_num);


--
-- Name: anexos_extension_contrato anexos_extension_contrato_pkey; Type: CONSTRAINT; Schema: public; Owner: rrhh_user
--

ALTER TABLE ONLY public.anexos_extension_contrato
    ADD CONSTRAINT anexos_extension_contrato_pkey PRIMARY KEY (id);


--
-- Name: bancos bancos_nombre_key; Type: CONSTRAINT; Schema: public; Owner: rrhh_user
--

ALTER TABLE ONLY public.bancos
    ADD CONSTRAINT bancos_nombre_key UNIQUE (nombre);


--
-- Name: bancos bancos_pkey; Type: CONSTRAINT; Schema: public; Owner: rrhh_user
--

ALTER TABLE ONLY public.bancos
    ADD CONSTRAINT bancos_pkey PRIMARY KEY (id);


--
-- Name: cajas_compensacion cajas_compensacion_nombre_key; Type: CONSTRAINT; Schema: public; Owner: rrhh_user
--

ALTER TABLE ONLY public.cajas_compensacion
    ADD CONSTRAINT cajas_compensacion_nombre_key UNIQUE (nombre);


--
-- Name: cajas_compensacion cajas_compensacion_pkey; Type: CONSTRAINT; Schema: public; Owner: rrhh_user
--

ALTER TABLE ONLY public.cajas_compensacion
    ADD CONSTRAINT cajas_compensacion_pkey PRIMARY KEY (id);


--
-- Name: cargos cargos_pkey; Type: CONSTRAINT; Schema: public; Owner: rrhh_user
--

ALTER TABLE ONLY public.cargos
    ADD CONSTRAINT cargos_pkey PRIMARY KEY (id);


--
-- Name: contratos contratos_pkey; Type: CONSTRAINT; Schema: public; Owner: rrhh_user
--

ALTER TABLE ONLY public.contratos
    ADD CONSTRAINT contratos_pkey PRIMARY KEY (id);


--
-- Name: documentos_laborales documentos_laborales_pkey; Type: CONSTRAINT; Schema: public; Owner: rrhh_user
--

ALTER TABLE ONLY public.documentos_laborales
    ADD CONSTRAINT documentos_laborales_pkey PRIMARY KEY (id);


--
-- Name: empleador_mutual empleador_mutual_pkey; Type: CONSTRAINT; Schema: public; Owner: rrhh_user
--

ALTER TABLE ONLY public.empleador_mutual
    ADD CONSTRAINT empleador_mutual_pkey PRIMARY KEY (id);


--
-- Name: empleadores empleadores_pkey; Type: CONSTRAINT; Schema: public; Owner: rrhh_user
--

ALTER TABLE ONLY public.empleadores
    ADD CONSTRAINT empleadores_pkey PRIMARY KEY (id);


--
-- Name: eventos_laborales eventos_laborales_pkey; Type: CONSTRAINT; Schema: public; Owner: rrhh_user
--

ALTER TABLE ONLY public.eventos_laborales
    ADD CONSTRAINT eventos_laborales_pkey PRIMARY KEY (id);


--
-- Name: horario_tramos horario_tramos_pkey; Type: CONSTRAINT; Schema: public; Owner: rrhh_user
--

ALTER TABLE ONLY public.horario_tramos
    ADD CONSTRAINT horario_tramos_pkey PRIMARY KEY (id);


--
-- Name: horarios horarios_nombre_key; Type: CONSTRAINT; Schema: public; Owner: rrhh_user
--

ALTER TABLE ONLY public.horarios
    ADD CONSTRAINT horarios_nombre_key UNIQUE (nombre);


--
-- Name: horarios horarios_pkey; Type: CONSTRAINT; Schema: public; Owner: rrhh_user
--

ALTER TABLE ONLY public.horarios
    ADD CONSTRAINT horarios_pkey PRIMARY KEY (id);


--
-- Name: mutuales mutuales_pkey; Type: CONSTRAINT; Schema: public; Owner: rrhh_user
--

ALTER TABLE ONLY public.mutuales
    ADD CONSTRAINT mutuales_pkey PRIMARY KEY (id);


--
-- Name: obras obras_codigo_key; Type: CONSTRAINT; Schema: public; Owner: rrhh_user
--

ALTER TABLE ONLY public.obras
    ADD CONSTRAINT obras_codigo_key UNIQUE (codigo);


--
-- Name: obras obras_pkey; Type: CONSTRAINT; Schema: public; Owner: rrhh_user
--

ALTER TABLE ONLY public.obras
    ADD CONSTRAINT obras_pkey PRIMARY KEY (id);


--
-- Name: roles roles_name_key; Type: CONSTRAINT; Schema: public; Owner: rrhh_user
--

ALTER TABLE ONLY public.roles
    ADD CONSTRAINT roles_name_key UNIQUE (name);


--
-- Name: roles roles_pkey; Type: CONSTRAINT; Schema: public; Owner: rrhh_user
--

ALTER TABLE ONLY public.roles
    ADD CONSTRAINT roles_pkey PRIMARY KEY (id);


--
-- Name: salud salud_nombre_key; Type: CONSTRAINT; Schema: public; Owner: rrhh_user
--

ALTER TABLE ONLY public.salud
    ADD CONSTRAINT salud_nombre_key UNIQUE (nombre);


--
-- Name: salud salud_pkey; Type: CONSTRAINT; Schema: public; Owner: rrhh_user
--

ALTER TABLE ONLY public.salud
    ADD CONSTRAINT salud_pkey PRIMARY KEY (id);


--
-- Name: trabajador_obras trabajador_obras_pkey; Type: CONSTRAINT; Schema: public; Owner: rrhh_user
--

ALTER TABLE ONLY public.trabajador_obras
    ADD CONSTRAINT trabajador_obras_pkey PRIMARY KEY (id);


--
-- Name: trabajadores trabajadores_pkey; Type: CONSTRAINT; Schema: public; Owner: rrhh_user
--

ALTER TABLE ONLY public.trabajadores
    ADD CONSTRAINT trabajadores_pkey PRIMARY KEY (id);


--
-- Name: trabajadores trabajadores_rut_key; Type: CONSTRAINT; Schema: public; Owner: rrhh_user
--

ALTER TABLE ONLY public.trabajadores
    ADD CONSTRAINT trabajadores_rut_key UNIQUE (rut);


--
-- Name: user_obras user_obras_pkey; Type: CONSTRAINT; Schema: public; Owner: rrhh_user
--

ALTER TABLE ONLY public.user_obras
    ADD CONSTRAINT user_obras_pkey PRIMARY KEY (user_id, obra_id);


--
-- Name: user_roles user_roles_pkey; Type: CONSTRAINT; Schema: public; Owner: rrhh_user
--

ALTER TABLE ONLY public.user_roles
    ADD CONSTRAINT user_roles_pkey PRIMARY KEY (user_id, role_id);


--
-- Name: users users_pkey; Type: CONSTRAINT; Schema: public; Owner: rrhh_user
--

ALTER TABLE ONLY public.users
    ADD CONSTRAINT users_pkey PRIMARY KEY (id);


--
-- Name: ix_anexos_extension_contrato_contrato_id; Type: INDEX; Schema: public; Owner: rrhh_user
--

CREATE INDEX ix_anexos_extension_contrato_contrato_id ON public.anexos_extension_contrato USING btree (contrato_id);


--
-- Name: ix_anexos_extension_contrato_empleador_id; Type: INDEX; Schema: public; Owner: rrhh_user
--

CREATE INDEX ix_anexos_extension_contrato_empleador_id ON public.anexos_extension_contrato USING btree (empleador_id);


--
-- Name: ix_anexos_extension_contrato_obra_id; Type: INDEX; Schema: public; Owner: rrhh_user
--

CREATE INDEX ix_anexos_extension_contrato_obra_id ON public.anexos_extension_contrato USING btree (obra_id);


--
-- Name: ix_anexos_extension_contrato_trabajador_id; Type: INDEX; Schema: public; Owner: rrhh_user
--

CREATE INDEX ix_anexos_extension_contrato_trabajador_id ON public.anexos_extension_contrato USING btree (trabajador_id);


--
-- Name: ix_contratos_horario_id; Type: INDEX; Schema: public; Owner: rrhh_user
--

CREATE INDEX ix_contratos_horario_id ON public.contratos USING btree (horario_id);


--
-- Name: ix_eventos_laborales_contrato_id; Type: INDEX; Schema: public; Owner: rrhh_user
--

CREATE INDEX ix_eventos_laborales_contrato_id ON public.eventos_laborales USING btree (contrato_id);


--
-- Name: ix_eventos_laborales_empleador_id; Type: INDEX; Schema: public; Owner: rrhh_user
--

CREATE INDEX ix_eventos_laborales_empleador_id ON public.eventos_laborales USING btree (empleador_id);


--
-- Name: ix_eventos_laborales_obra_id; Type: INDEX; Schema: public; Owner: rrhh_user
--

CREATE INDEX ix_eventos_laborales_obra_id ON public.eventos_laborales USING btree (obra_id);


--
-- Name: ix_eventos_laborales_trabajador_id; Type: INDEX; Schema: public; Owner: rrhh_user
--

CREATE INDEX ix_eventos_laborales_trabajador_id ON public.eventos_laborales USING btree (trabajador_id);


--
-- Name: ix_horario_tramos_horario_id; Type: INDEX; Schema: public; Owner: rrhh_user
--

CREATE INDEX ix_horario_tramos_horario_id ON public.horario_tramos USING btree (horario_id);


--
-- Name: ix_trabajador_obras_obra_id; Type: INDEX; Schema: public; Owner: rrhh_user
--

CREATE INDEX ix_trabajador_obras_obra_id ON public.trabajador_obras USING btree (obra_id);


--
-- Name: ix_trabajador_obras_trabajador_id; Type: INDEX; Schema: public; Owner: rrhh_user
--

CREATE INDEX ix_trabajador_obras_trabajador_id ON public.trabajador_obras USING btree (trabajador_id);


--
-- Name: ix_users_email; Type: INDEX; Schema: public; Owner: rrhh_user
--

CREATE UNIQUE INDEX ix_users_email ON public.users USING btree (email);


--
-- Name: ix_users_username; Type: INDEX; Schema: public; Owner: rrhh_user
--

CREATE UNIQUE INDEX ix_users_username ON public.users USING btree (username);


--
-- Name: anexos_extension_contrato anexos_extension_contrato_contrato_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: rrhh_user
--

ALTER TABLE ONLY public.anexos_extension_contrato
    ADD CONSTRAINT anexos_extension_contrato_contrato_id_fkey FOREIGN KEY (contrato_id) REFERENCES public.contratos(id);


--
-- Name: anexos_extension_contrato anexos_extension_contrato_empleador_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: rrhh_user
--

ALTER TABLE ONLY public.anexos_extension_contrato
    ADD CONSTRAINT anexos_extension_contrato_empleador_id_fkey FOREIGN KEY (empleador_id) REFERENCES public.empleadores(id);


--
-- Name: anexos_extension_contrato anexos_extension_contrato_obra_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: rrhh_user
--

ALTER TABLE ONLY public.anexos_extension_contrato
    ADD CONSTRAINT anexos_extension_contrato_obra_id_fkey FOREIGN KEY (obra_id) REFERENCES public.obras(id);


--
-- Name: anexos_extension_contrato anexos_extension_contrato_trabajador_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: rrhh_user
--

ALTER TABLE ONLY public.anexos_extension_contrato
    ADD CONSTRAINT anexos_extension_contrato_trabajador_id_fkey FOREIGN KEY (trabajador_id) REFERENCES public.trabajadores(id);


--
-- Name: contratos contratos_cargo_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: rrhh_user
--

ALTER TABLE ONLY public.contratos
    ADD CONSTRAINT contratos_cargo_id_fkey FOREIGN KEY (cargo_id) REFERENCES public.cargos(id);


--
-- Name: contratos contratos_empleador_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: rrhh_user
--

ALTER TABLE ONLY public.contratos
    ADD CONSTRAINT contratos_empleador_id_fkey FOREIGN KEY (empleador_id) REFERENCES public.empleadores(id);


--
-- Name: contratos contratos_obra_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: rrhh_user
--

ALTER TABLE ONLY public.contratos
    ADD CONSTRAINT contratos_obra_id_fkey FOREIGN KEY (obra_id) REFERENCES public.obras(id);


--
-- Name: contratos contratos_trabajador_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: rrhh_user
--

ALTER TABLE ONLY public.contratos
    ADD CONSTRAINT contratos_trabajador_id_fkey FOREIGN KEY (trabajador_id) REFERENCES public.trabajadores(id);


--
-- Name: documentos_laborales documentos_laborales_contrato_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: rrhh_user
--

ALTER TABLE ONLY public.documentos_laborales
    ADD CONSTRAINT documentos_laborales_contrato_id_fkey FOREIGN KEY (contrato_id) REFERENCES public.contratos(id);


--
-- Name: empleador_mutual empleador_mutual_empleador_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: rrhh_user
--

ALTER TABLE ONLY public.empleador_mutual
    ADD CONSTRAINT empleador_mutual_empleador_id_fkey FOREIGN KEY (empleador_id) REFERENCES public.empleadores(id);


--
-- Name: empleador_mutual empleador_mutual_mutual_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: rrhh_user
--

ALTER TABLE ONLY public.empleador_mutual
    ADD CONSTRAINT empleador_mutual_mutual_id_fkey FOREIGN KEY (mutual_id) REFERENCES public.mutuales(id);


--
-- Name: eventos_laborales eventos_laborales_contrato_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: rrhh_user
--

ALTER TABLE ONLY public.eventos_laborales
    ADD CONSTRAINT eventos_laborales_contrato_id_fkey FOREIGN KEY (contrato_id) REFERENCES public.contratos(id);


--
-- Name: eventos_laborales eventos_laborales_empleador_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: rrhh_user
--

ALTER TABLE ONLY public.eventos_laborales
    ADD CONSTRAINT eventos_laborales_empleador_id_fkey FOREIGN KEY (empleador_id) REFERENCES public.empleadores(id);


--
-- Name: eventos_laborales eventos_laborales_obra_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: rrhh_user
--

ALTER TABLE ONLY public.eventos_laborales
    ADD CONSTRAINT eventos_laborales_obra_id_fkey FOREIGN KEY (obra_id) REFERENCES public.obras(id);


--
-- Name: eventos_laborales eventos_laborales_trabajador_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: rrhh_user
--

ALTER TABLE ONLY public.eventos_laborales
    ADD CONSTRAINT eventos_laborales_trabajador_id_fkey FOREIGN KEY (trabajador_id) REFERENCES public.trabajadores(id);


--
-- Name: contratos fk_contratos_horario_id; Type: FK CONSTRAINT; Schema: public; Owner: rrhh_user
--

ALTER TABLE ONLY public.contratos
    ADD CONSTRAINT fk_contratos_horario_id FOREIGN KEY (horario_id) REFERENCES public.horarios(id);


--
-- Name: horario_tramos horario_tramos_horario_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: rrhh_user
--

ALTER TABLE ONLY public.horario_tramos
    ADD CONSTRAINT horario_tramos_horario_id_fkey FOREIGN KEY (horario_id) REFERENCES public.horarios(id);


--
-- Name: obras obras_empleador_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: rrhh_user
--

ALTER TABLE ONLY public.obras
    ADD CONSTRAINT obras_empleador_id_fkey FOREIGN KEY (empleador_id) REFERENCES public.empleadores(id);


--
-- Name: trabajador_obras trabajador_obras_obra_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: rrhh_user
--

ALTER TABLE ONLY public.trabajador_obras
    ADD CONSTRAINT trabajador_obras_obra_id_fkey FOREIGN KEY (obra_id) REFERENCES public.obras(id);


--
-- Name: trabajador_obras trabajador_obras_trabajador_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: rrhh_user
--

ALTER TABLE ONLY public.trabajador_obras
    ADD CONSTRAINT trabajador_obras_trabajador_id_fkey FOREIGN KEY (trabajador_id) REFERENCES public.trabajadores(id);


--
-- Name: trabajadores trabajadores_afp_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: rrhh_user
--

ALTER TABLE ONLY public.trabajadores
    ADD CONSTRAINT trabajadores_afp_id_fkey FOREIGN KEY (afp_id) REFERENCES public.afp(id);


--
-- Name: trabajadores trabajadores_banco_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: rrhh_user
--

ALTER TABLE ONLY public.trabajadores
    ADD CONSTRAINT trabajadores_banco_id_fkey FOREIGN KEY (banco_id) REFERENCES public.bancos(id);


--
-- Name: trabajadores trabajadores_caja_compensacion_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: rrhh_user
--

ALTER TABLE ONLY public.trabajadores
    ADD CONSTRAINT trabajadores_caja_compensacion_id_fkey FOREIGN KEY (caja_compensacion_id) REFERENCES public.cajas_compensacion(id);


--
-- Name: trabajadores trabajadores_cargo_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: rrhh_user
--

ALTER TABLE ONLY public.trabajadores
    ADD CONSTRAINT trabajadores_cargo_id_fkey FOREIGN KEY (cargo_id) REFERENCES public.cargos(id);


--
-- Name: trabajadores trabajadores_obra_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: rrhh_user
--

ALTER TABLE ONLY public.trabajadores
    ADD CONSTRAINT trabajadores_obra_id_fkey FOREIGN KEY (obra_id) REFERENCES public.obras(id);


--
-- Name: trabajadores trabajadores_pago_tercero_banco_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: rrhh_user
--

ALTER TABLE ONLY public.trabajadores
    ADD CONSTRAINT trabajadores_pago_tercero_banco_id_fkey FOREIGN KEY (pago_tercero_banco_id) REFERENCES public.bancos(id);


--
-- Name: trabajadores trabajadores_salud_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: rrhh_user
--

ALTER TABLE ONLY public.trabajadores
    ADD CONSTRAINT trabajadores_salud_id_fkey FOREIGN KEY (salud_id) REFERENCES public.salud(id);


--
-- Name: user_obras user_obras_obra_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: rrhh_user
--

ALTER TABLE ONLY public.user_obras
    ADD CONSTRAINT user_obras_obra_id_fkey FOREIGN KEY (obra_id) REFERENCES public.obras(id);


--
-- Name: user_obras user_obras_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: rrhh_user
--

ALTER TABLE ONLY public.user_obras
    ADD CONSTRAINT user_obras_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id);


--
-- Name: user_roles user_roles_role_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: rrhh_user
--

ALTER TABLE ONLY public.user_roles
    ADD CONSTRAINT user_roles_role_id_fkey FOREIGN KEY (role_id) REFERENCES public.roles(id);


--
-- Name: user_roles user_roles_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: rrhh_user
--

ALTER TABLE ONLY public.user_roles
    ADD CONSTRAINT user_roles_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id);


--
-- PostgreSQL database dump complete
--

\unrestrict NQx3u3ROmSvzcdJI3xFeKH75O9dRLOTXg5jTTXWvFSgc2I4jKsmvPY8MueITC02

