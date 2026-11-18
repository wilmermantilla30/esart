
CREATE TABLE esart.permisos (
	id UUID DEFAULT gen_random_uuid() NOT NULL, 
	codigo VARCHAR(50) NOT NULL, 
	descripcion VARCHAR(200) NOT NULL, 
	fecha_creacion TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	fecha_actualizacion TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT hu0304_permisos_uq_permisos_codigo UNIQUE (codigo)
)

;


CREATE TABLE esart.tipos_certificacion (
	id UUID DEFAULT gen_random_uuid() NOT NULL, 
	codigo VARCHAR(30) NOT NULL, 
	nombre VARCHAR(200) NOT NULL, 
	entidad_emisora VARCHAR(200), 
	tipo_sistema VARCHAR(50), 
	activo BOOLEAN DEFAULT true NOT NULL, 
	fecha_creacion TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	fecha_actualizacion TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT hu0304_tipos_certificacion_uq_tipos_certificacion_codigo UNIQUE (codigo)
)

;


CREATE TABLE esart.tipos_unidad (
	id UUID DEFAULT gen_random_uuid() NOT NULL, 
	codigo VARCHAR(20) NOT NULL, 
	nombre VARCHAR(200) NOT NULL, 
	activo BOOLEAN DEFAULT true NOT NULL, 
	fecha_creacion TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	fecha_actualizacion TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT hu0304_tipos_unidad_ck_tipos_unidad_codigo CHECK (codigo ~ '^[A-Z][A-Z0-9_]{0,19}$'), 
	CONSTRAINT hu0304_tipos_unidad_ck_tipos_unidad_nombre CHECK (length(btrim(nombre)) > 0), 
	CONSTRAINT hu0304_tipos_unidad_uq_tipos_unidad_codigo UNIQUE (codigo)
)

;


CREATE TABLE esart.requisitos_habilitacion (
	id UUID DEFAULT gen_random_uuid() NOT NULL, 
	sistema_artilleria_id BIGINT, 
	tipo_requisito VARCHAR(20) NOT NULL, 
	tipo_curso_id BIGINT, 
	tipo_certificacion_id UUID, 
	descripcion VARCHAR(300) NOT NULL, 
	activo BOOLEAN DEFAULT true NOT NULL, 
	fecha_creacion TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	fecha_actualizacion TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT hu0304_requisitos_habilitacion_ck_requisitos_ha_fb04cad2f111 CHECK ((tipo_requisito = 'CURSO' AND tipo_curso_id IS NOT NULL AND tipo_certificacion_id IS NULL) OR (tipo_requisito = 'CERTIFICACION' AND tipo_certificacion_id IS NOT NULL AND tipo_curso_id IS NULL)), 
	CONSTRAINT hu0304_requisitos_habilitacion_ck_requisitos_ha_e18a13bbc247 CHECK (tipo_requisito IN ('CURSO','CERTIFICACION')), 
	CONSTRAINT hu0304_requisitos_habilitacion_fk_requisitos_ha_3ce674ec75e5 FOREIGN KEY(sistema_artilleria_id) REFERENCES esart_ref.sistemas_artilleria (id), 
	CONSTRAINT hu0304_requisitos_habilitacion_fk_requisitos_ha_873282e5530d FOREIGN KEY(tipo_certificacion_id) REFERENCES esart.tipos_certificacion (id), 
	CONSTRAINT hu0304_requisitos_habilitacion_fk_requisitos_ha_54d0a04888e5 FOREIGN KEY(tipo_curso_id) REFERENCES esart.tipos_curso (id)
)

;


CREATE TABLE esart.roles_permisos (
	rol_id BIGINT NOT NULL, 
	permiso_id UUID NOT NULL, 
	fecha_creacion TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	fecha_actualizacion TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	PRIMARY KEY (rol_id, permiso_id), 
	CONSTRAINT hu0304_roles_permisos_fk_roles_permisos_permiso_id_permisos FOREIGN KEY(permiso_id) REFERENCES esart.permisos (id), 
	CONSTRAINT hu0304_roles_permisos_fk_roles_permisos_rol_id_roles FOREIGN KEY(rol_id) REFERENCES esart.roles (id)
)

;


CREATE TABLE esart.auditoria_eventos (
	id BIGINT GENERATED ALWAYS AS IDENTITY, 
	fecha TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	usuario_id BIGINT, 
	nombre_usuario VARCHAR(60), 
	accion VARCHAR(40) NOT NULL, 
	numero_documento_consultado VARCHAR(10), 
	resultado VARCHAR(20), 
	direccion_ip INET, 
	agente_usuario VARCHAR(300), 
	detalle JSONB, 
	PRIMARY KEY (id), 
	CONSTRAINT hu0304_auditoria_eventos_ck_auditoria_eventos_accion CHECK (accion IN ('LOGIN_EXITOSO','LOGIN_FALLIDO','USUARIO_BLOQUEADO','USUARIO_DESBLOQUEADO','CONSULTA_ARTILLERO','CONSULTA_HABILITADOS','CONSULTA_NO_HABILITADOS','IMPORTACION_EXCEL','CIERRE_SESION')), 
	CONSTRAINT hu0304_auditoria_eventos_fk_auditoria_eventos_u_f5c0fef721f3 FOREIGN KEY(usuario_id) REFERENCES esart_ref.usuarios (id)
)

;


CREATE TABLE esart.importaciones_excel (
	id UUID DEFAULT gen_random_uuid() NOT NULL, 
	usuario_id BIGINT NOT NULL, 
	nombre_archivo VARCHAR(255) NOT NULL, 
	hash_sha256_archivo CHAR(64) NOT NULL, 
	fecha TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	filas_totales INTEGER DEFAULT 0 NOT NULL, 
	filas_validas INTEGER DEFAULT 0 NOT NULL, 
	filas_rechazadas INTEGER DEFAULT 0 NOT NULL, 
	estado VARCHAR(20) NOT NULL, 
	errores JSONB, 
	fecha_creacion TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	fecha_actualizacion TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT hu0304_importaciones_excel_ck_importaciones_excel_estado CHECK (estado IN ('PROCESANDO','APLICADA','RECHAZADA')), 
	CONSTRAINT hu0304_importaciones_excel_fk_importaciones_exc_52341dfbf393 FOREIGN KEY(usuario_id) REFERENCES esart_ref.usuarios (id), 
	CONSTRAINT hu0304_importaciones_excel_uq_importaciones_exc_930b7f6e0326 UNIQUE (hash_sha256_archivo)
)

;


CREATE TABLE esart.intentos_inicio_sesion (
	id BIGINT GENERATED ALWAYS AS IDENTITY, 
	nombre_usuario_intentado VARCHAR(60) NOT NULL, 
	usuario_id BIGINT, 
	direccion_ip INET, 
	exitoso BOOLEAN NOT NULL, 
	motivo_fallo VARCHAR(40), 
	fecha TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT hu0304_intentos_inicio_sesion_fk_intentos_inici_ee93bab4317c FOREIGN KEY(usuario_id) REFERENCES esart_ref.usuarios (id)
)

;


CREATE TABLE esart.sesiones_usuario (
	id UUID NOT NULL, 
	usuario_id BIGINT NOT NULL, 
	fecha_inicio TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	fecha_ultima_actividad TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	direccion_ip INET, 
	agente_usuario VARCHAR(300), 
	revocada BOOLEAN DEFAULT false NOT NULL, 
	fecha_revocacion TIMESTAMP WITH TIME ZONE, 
	PRIMARY KEY (id), 
	CONSTRAINT hu0304_sesiones_usuario_fk_sesiones_usuario_usu_9a7eb8fa3824 FOREIGN KEY(usuario_id) REFERENCES esart_ref.usuarios (id)
)

;

ALTER TABLE esart_ref.unidades_militares ADD COLUMN codigo VARCHAR(20);

ALTER TABLE esart_ref.unidades_militares ADD COLUMN nombre VARCHAR(200);

ALTER TABLE esart_ref.unidades_militares ADD COLUMN sigla VARCHAR(30);

ALTER TABLE esart_ref.unidades_militares ADD COLUMN unidad_superior_id BIGINT;

ALTER TABLE esart_ref.unidades_militares ADD COLUMN activa BOOLEAN;

ALTER TABLE esart_ref.unidades_militares ADD COLUMN fecha_creacion TIMESTAMP WITH TIME ZONE;

ALTER TABLE esart_ref.unidades_militares ADD COLUMN fecha_actualizacion TIMESTAMP WITH TIME ZONE;

ALTER TABLE esart_ref.unidades_militares ADD COLUMN tipo_unidad_id UUID;

ALTER TABLE esart_ref.unidades_militares ADD COLUMN uuid_publico UUID;

ALTER TABLE esart.personal_militar ADD COLUMN primer_nombre VARCHAR(60);

ALTER TABLE esart.personal_militar ADD COLUMN segundo_nombre VARCHAR(60);

ALTER TABLE esart.personal_militar ADD COLUMN primer_apellido VARCHAR(60);

ALTER TABLE esart.personal_militar ADD COLUMN segundo_apellido VARCHAR(60);

ALTER TABLE esart.personal_militar ADD COLUMN arma VARCHAR(40);

ALTER TABLE esart.personal_militar ADD COLUMN estado_servicio VARCHAR(20);

ALTER TABLE esart.hoja_vida_artillero ADD COLUMN especialidad VARCHAR(100);

ALTER TABLE esart.hoja_vida_artillero ADD COLUMN fecha_ingreso_arma DATE;

ALTER TABLE esart.roles ADD COLUMN fecha_actualizacion TIMESTAMP WITH TIME ZONE;

ALTER TABLE esart_ref.usuarios ADD COLUMN nombre_completo VARCHAR(200);

ALTER TABLE esart_ref.usuarios ADD COLUMN rol_id BIGINT;

ALTER TABLE esart_ref.usuarios ADD COLUMN intentos_fallidos_consecutivos INTEGER;

ALTER TABLE esart_ref.usuarios ADD COLUMN bloqueado_hasta TIMESTAMP WITH TIME ZONE;

ALTER TABLE esart.tipos_curso ADD COLUMN descripcion TEXT;

ALTER TABLE esart.tipos_curso ADD COLUMN tipo_sistema VARCHAR(50);

ALTER TABLE esart.tipos_curso ADD COLUMN vigencia_meses INTEGER;

ALTER TABLE esart.tipos_curso ADD COLUMN nota_minima_aprobacion NUMERIC(4, 2);

ALTER TABLE esart.tipos_curso ADD COLUMN fecha_creacion TIMESTAMP WITH TIME ZONE;

ALTER TABLE esart.tipos_curso ADD COLUMN fecha_actualizacion TIMESTAMP WITH TIME ZONE;

ALTER TABLE esart.artillero_cursos ADD COLUMN numero_cohorte VARCHAR(30);

ALTER TABLE esart.artillero_cursos ADD COLUMN estado VARCHAR(20);

ALTER TABLE esart.artillero_cursos ADD COLUMN nota_final NUMERIC(4, 2);

ALTER TABLE esart.artillero_cursos ADD COLUMN numero_acta VARCHAR(50);

ALTER TABLE esart.artillero_cursos ADD COLUMN importacion_excel_id UUID;

ALTER TABLE esart.artillero_cursos ADD COLUMN fecha_actualizacion TIMESTAMP WITH TIME ZONE;

ALTER TABLE esart.artillero_certificaciones ADD COLUMN tipo_certificacion_id UUID;

ALTER TABLE esart.artillero_certificaciones ADD COLUMN numero_certificado VARCHAR(50);

ALTER TABLE esart.artillero_certificaciones ADD COLUMN estado VARCHAR(20);

ALTER TABLE esart.artillero_certificaciones ADD COLUMN importacion_excel_id UUID;

ALTER TABLE esart.artillero_certificaciones ADD COLUMN fecha_actualizacion TIMESTAMP WITH TIME ZONE;

ALTER TABLE esart_ref.sistemas_artilleria ADD COLUMN codigo VARCHAR(30);

ALTER TABLE esart_ref.sistemas_artilleria ADD COLUMN nombre VARCHAR(200);

ALTER TABLE esart_ref.sistemas_artilleria ADD COLUMN tipo_sistema VARCHAR(50);

ALTER TABLE esart_ref.sistemas_artilleria ADD COLUMN calibre_milimetros NUMERIC(6, 2);

ALTER TABLE esart_ref.sistemas_artilleria ADD COLUMN verificacion_habilitada BOOLEAN;

ALTER TABLE esart_ref.sistemas_artilleria ADD COLUMN activo BOOLEAN;

ALTER TABLE esart_ref.sistemas_artilleria ADD COLUMN fecha_creacion TIMESTAMP WITH TIME ZONE;

ALTER TABLE esart_ref.sistemas_artilleria ADD COLUMN fecha_actualizacion TIMESTAMP WITH TIME ZONE;

ALTER TABLE esart.tipos_cargo ADD COLUMN codigo VARCHAR(30);

ALTER TABLE esart.tipos_cargo ADD COLUMN fecha_actualizacion TIMESTAMP WITH TIME ZONE;

ALTER TABLE esart.artillero_cargos ADD COLUMN numero_resolucion VARCHAR(50);

ALTER TABLE esart.artillero_cargos ADD COLUMN fecha_actualizacion TIMESTAMP WITH TIME ZONE;

ALTER TABLE esart.componentes ADD COLUMN fecha_actualizacion TIMESTAMP WITH TIME ZONE;

ALTER TABLE esart.rol_permisos ADD COLUMN fecha_creacion TIMESTAMP WITH TIME ZONE;

ALTER TABLE esart.usuario_permisos ADD COLUMN fecha_creacion TIMESTAMP WITH TIME ZONE;

ALTER TABLE esart_ref.unidades_militares ADD CONSTRAINT hu0304_unidades_militares_fk_unidades_militares_9c7b26df19cd FOREIGN KEY(tipo_unidad_id) REFERENCES esart.tipos_unidad (id) ON DELETE RESTRICT;

ALTER TABLE esart_ref.unidades_militares ADD CONSTRAINT hu0304_unidades_militares_fk_unidades_militares_f5941a517314 FOREIGN KEY(unidad_superior_id) REFERENCES esart_ref.unidades_militares (id);

ALTER TABLE esart_ref.unidades_militares ADD CONSTRAINT hu0304_unidades_militares_uq_unidades_militares_codigo UNIQUE (codigo);

ALTER TABLE esart_ref.unidades_militares ADD CONSTRAINT hu0304_unidades_uuid_publico UNIQUE (uuid_publico);

ALTER TABLE esart_ref.unidades_militares ADD CONSTRAINT hu0304_unidades_no_autosuperior CHECK (unidad_superior_id IS DISTINCT FROM id);

ALTER TABLE esart.personal_militar ADD CONSTRAINT hu0304_personal_militar_ck_personal_militar_categoria CHECK (categoria IN ('OFICIAL','SUBOFICIAL','SOLDADO_PROFESIONAL','CIVIL'));

ALTER TABLE esart.personal_militar ADD CONSTRAINT hu0304_personal_militar_ck_personal_militar_estado_servicio CHECK (estado_servicio IN ('ACTIVO','RETIRADO','SUSPENDIDO','COMISION','LICENCIA'));

ALTER TABLE esart.personal_militar ADD CONSTRAINT hu0304_personal_militar_ck_personal_militar_numero_documento CHECK (documento_identidad ~ '^[0-9]{6,10}$');

ALTER TABLE esart_ref.usuarios ADD CONSTRAINT hu0304_usuarios_fk_usuarios_rol_id_roles FOREIGN KEY(rol_id) REFERENCES esart.roles (id);

ALTER TABLE esart.tipos_curso ADD CONSTRAINT hu0304_tipos_curso_ck_tipos_curso_nota_minima_aprobacion CHECK (nota_minima_aprobacion BETWEEN 0 AND 5);

ALTER TABLE esart.tipos_curso ADD CONSTRAINT hu0304_tipos_curso_ck_tipos_curso_vigencia_meses CHECK (vigencia_meses > 0);

ALTER TABLE esart.artillero_cursos ADD CONSTRAINT hu0304_artillero_cursos_ck_artillero_cursos_estado CHECK (estado IN ('EN_CURSO','APROBADO','REPROBADO','RETIRADO','ANULADO'));

ALTER TABLE esart.artillero_cursos ADD CONSTRAINT hu0304_artillero_cursos_ck_artillero_cursos_nota_final CHECK (nota_final BETWEEN 0 AND 5);

ALTER TABLE esart.artillero_cursos ADD CONSTRAINT hu0304_artillero_cursos_fk_artillero_cursos_imp_d60f97ed496d FOREIGN KEY(importacion_excel_id) REFERENCES esart.importaciones_excel (id);

ALTER TABLE esart.artillero_cursos ADD CONSTRAINT hu0304_artillero_cursos_uq_artillero_cursos_hoj_1cded9c13419 UNIQUE (hoja_vida_id, tipo_curso_id, numero_cohorte);

ALTER TABLE esart.artillero_certificaciones ADD CONSTRAINT hu0304_artillero_certificaciones_ck_artillero_c_a6c77dbed03b CHECK (estado IN ('ACTIVA','SUSPENDIDA','REVOCADA'));

ALTER TABLE esart.artillero_certificaciones ADD CONSTRAINT hu0304_artillero_certificaciones_fk_artillero_c_dd7d578fe0fd FOREIGN KEY(importacion_excel_id) REFERENCES esart.importaciones_excel (id);

ALTER TABLE esart.artillero_certificaciones ADD CONSTRAINT hu0304_artillero_certificaciones_fk_artillero_c_1f73122ae7eb FOREIGN KEY(tipo_certificacion_id) REFERENCES esart.tipos_certificacion (id);

ALTER TABLE esart_ref.sistemas_artilleria ADD CONSTRAINT hu0304_sistemas_artilleria_uq_sistemas_artilleria_codigo UNIQUE (codigo);

ALTER TABLE esart.tipos_cargo ADD CONSTRAINT hu0304_tipos_cargo_uq_tipos_cargo_codigo UNIQUE (codigo);

CREATE INDEX hu0304_ix_unidades_militares_0 ON esart_ref.unidades_militares (tipo_unidad_id);

CREATE INDEX hu0304_ix_unidades_militares_1 ON esart_ref.unidades_militares (unidad_superior_id);

CREATE INDEX hu0304_ix_personal_militar_0 ON esart.personal_militar (estado_servicio);

CREATE INDEX hu0304_ix_personal_militar_1 ON esart.personal_militar (unidad_actual_id);

CREATE INDEX hu0304_ix_roles_permisos_0 ON esart.roles_permisos (permiso_id);

CREATE INDEX hu0304_ix_roles_permisos_1 ON esart.roles_permisos (rol_id);

CREATE INDEX hu0304_ix_usuarios_0 ON esart_ref.usuarios (rol_id);

CREATE UNIQUE INDEX hu0304_ix_usuarios_1 ON esart_ref.usuarios (lower(usuario));

CREATE INDEX hu0304_ix_intentos_inicio_sesion_0 ON esart.intentos_inicio_sesion (direccion_ip, fecha);

CREATE INDEX hu0304_ix_intentos_inicio_sesion_1 ON esart.intentos_inicio_sesion (usuario_id);

CREATE INDEX hu0304_ix_intentos_inicio_sesion_2 ON esart.intentos_inicio_sesion (usuario_id, fecha);

CREATE INDEX hu0304_ix_sesiones_usuario_0 ON esart.sesiones_usuario (usuario_id);

CREATE INDEX hu0304_ix_importaciones_excel_0 ON esart.importaciones_excel (usuario_id);

CREATE INDEX hu0304_ix_auditoria_eventos_0 ON esart.auditoria_eventos (fecha);

CREATE INDEX hu0304_ix_auditoria_eventos_1 ON esart.auditoria_eventos (numero_documento_consultado);

CREATE INDEX hu0304_ix_auditoria_eventos_2 ON esart.auditoria_eventos (usuario_id);

CREATE INDEX hu0304_ix_auditoria_eventos_3 ON esart.auditoria_eventos (usuario_id, fecha);

CREATE INDEX hu0304_ix_artillero_cursos_0 ON esart.artillero_cursos (hoja_vida_id, tipo_curso_id, estado);

CREATE INDEX hu0304_ix_artillero_cursos_2 ON esart.artillero_cursos (importacion_excel_id);

CREATE INDEX hu0304_ix_artillero_certificaciones_0 ON esart.artillero_certificaciones (hoja_vida_id, tipo_certificacion_id, estado, fecha_vencimiento);

CREATE INDEX hu0304_ix_artillero_certificaciones_2 ON esart.artillero_certificaciones (importacion_excel_id);

CREATE INDEX hu0304_ix_artillero_certificaciones_3 ON esart.artillero_certificaciones (tipo_certificacion_id);

CREATE INDEX hu0304_ix_requisitos_habilitacion_0 ON esart.requisitos_habilitacion (sistema_artilleria_id);

CREATE INDEX hu0304_ix_requisitos_habilitacion_1 ON esart.requisitos_habilitacion (tipo_certificacion_id);

CREATE INDEX hu0304_ix_requisitos_habilitacion_2 ON esart.requisitos_habilitacion (tipo_curso_id);

CREATE INDEX hu0304_ix_artillero_cargos_2 ON esart.artillero_cargos (unidad_id);

CREATE INDEX hu0304_ix_rol_permisos_1 ON esart.rol_permisos (rol_id);

CREATE INDEX hu0304_ix_usuario_permisos_0 ON esart.usuario_permisos (actualizado_por_id);

CREATE INDEX hu0304_ix_usuario_permisos_2 ON esart.usuario_permisos (usuario_id);
