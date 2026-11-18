> Documento de propuesta historica. La ejecucion autorizada y el estado actual de ambas bases estan en [HU04_FASE3_EJECUCION.md](HU04_FASE3_EJECUCION.md). Las reversiones solo se permiten en la base temporal.

# HU-04 fase 3: analisis tecnico previo

Estado: propuesta pendiente de aprobacion estructural. No se ha ejecutado 0002.

Alcance confirmado por el usuario: exclusivamente tipos de unidad militar.
Los cuatro estados operacionales y ocho logisticos pertenecen a VULCANO y quedan
fuera del alcance actual. Esta decision de alcance no autoriza ejecutar DDL.

Inspeccion real de solo lectura: esart_hu03_pruebas conserva revision 0001,
22 tablas de aplicacion mas alembic_version, 28 FK y 40 unidades. No existe tabla,
columna ni relacion equivalente para clasificar unidades. Evidencia completa:
backend/seeds/inspeccion_organizacion_fase3.json. Las columnas sigla y nombre no
son catalogos normalizados; el codigo de una unidad tampoco determina su tipo.
Las etiquetas de referencia no justifican clasificar automaticamente casos como
FUTOM. No se modificaran las filas existentes para completar esta clasificacion.

## Fuentes y alcance

Se revisaron los 22 modelos registrados, revision 0001, contratos de esquema y API,
README, informe HU-03, SQL de referencia ESART/Vulcano y literales heredados.
El alcance vigente verifica la habilitacion del artillero. La gestion operacional
y logistica del material no aparece como flujo activo en el contrato de API.

## Decision propuesta por catalogo

| Catalogo | Equivalente vigente | Propuesta y justificacion |
|---|---|---|
| Tipos de unidad (9) | Ninguno. tipos_cargo clasifica cargos; unidad_superior_id expresa jerarquia, no clase institucional. | Proponer tipos_unidad como extension organizacional de ESART, con FK opcional en unidades_militares. Requiere aprobacion del cambio de contrato. |
| Estados operacionales (4) | Ninguno. estado_servicio es del personal; activa es visibilidad de la unidad; activo de sistemas no describe su ciclo operativo. | Diferir: los valores EN_OPERACION/EN_BATALLON/PENDIENTE_BAJA/DADO_BAJA describen material de Vulcano. No vincularlos a unidades ni a personas. |
| Estados logisticos (8) | Ninguno. Los estados de cursos, certificaciones e importaciones pertenecen a otros dominios. | Diferir: mantenimiento/abastecimiento/baja/duplicidad describen instancias de material. No hay sistemas_en_operacion en las 22 tablas. |

Los permisos heredados cargados en fase 2 no constituyen por si mismos aprobacion
de esos modulos. sistemas_artilleria se usa como catalogo de sistemas para requisitos
de habilitacion; no acredita la existencia de inventario de piezas operacionales.
El SQL alternativo solo contiene un stub BIGINT sistemas_en_operacion. No reutilizarlo
como modelo UUID ni crear estados sin una entidad consumidora definida.

## Arquitectura 0002 propuesta

- Una tabla public.tipos_unidad: id UUID PK default gen_random_uuid(); codigo varchar(20)
  NOT NULL UNIQUE CHECK formato mayusculas; nombre varchar(200) NOT NULL CHECK texto
  no vacio; activo boolean NOT NULL default true; fecha_creacion y fecha_actualizacion
  timestamptz NOT NULL default now(). Se reutiliza el trigger de actualizacion de 0001.
- Una columna nullable unidades_militares.tipo_unidad_id UUID, sin default, con indice
  individual y FK tipos_unidad.id ON DELETE RESTRICT. Muchos registros de unidad
  pueden compartir un tipo. El tipo no determina el superior ni impone niveles nuevos.
- No se asignan tipos a las 40 unidades existentes ni se infiere la clasificacion por
  prefijo. NULL significa clasificacion pendiente, no una clase inventada.
- Los seeds solo insertan los 9 tipos mediante ON CONFLICT(codigo) DO NOTHING.
  Textos diferentes se informan y conservan. No actualizan unidades ni otros catalogos.
- Los 4+8 estados se conservan como referencia validada; no se cargan ni se crean
  modelos/tablas especulativos. Si se aprueba ampliar ESART al material operativo,
  antes se debe definir la entidad de inventario y su relacion con unidad/sistema,
  cardinalidad e historial. Sus FK pertenecerian al material, no a unidades_militares.
- Reversion 0002->0001 solo cuando tipos_unidad esta vacia y no hay clasificaciones.
  Se rechaza perder filas de catalogo o valores tipo_unidad_id. No existe un unseed
  que borre datos automaticamente. Las pruebas de reversion usan rollback de semillas.

## Inventario completo de HU-03

El siguiente inventario se genera desde los metadatos anteriores a la propuesta.
Todas las columnas se muestran con tipo, nulabilidad, PK y FK; se incluyen CHECK y UNIQUE.

### unidades_militares

| Columna | Tipo | NULL | Restricciones |
|---|---|---|---|
| id | CHAR(32) | no | PK |
| codigo | VARCHAR(20) | no |  |
| nombre | VARCHAR(200) | no |  |
| sigla | VARCHAR(30) | si |  |
| unidad_superior_id | CHAR(32) | si | FK -> unidades_militares.id |
| activa | BOOLEAN | no |  |
| fecha_creacion | DATETIME | no |  |
| fecha_actualizacion | DATETIME | no |  |

UNIQUE: `codigo`.

### personal_militar

| Columna | Tipo | NULL | Restricciones |
|---|---|---|---|
| id | CHAR(32) | no | PK |
| numero_documento | VARCHAR(10) | no |  |
| primer_nombre | VARCHAR(60) | no |  |
| segundo_nombre | VARCHAR(60) | si |  |
| primer_apellido | VARCHAR(60) | no |  |
| segundo_apellido | VARCHAR(60) | si |  |
| grado | VARCHAR(40) | no |  |
| categoria | VARCHAR(20) | no |  |
| arma | VARCHAR(40) | si |  |
| unidad_militar_id | CHAR(32) | si | FK -> unidades_militares.id |
| estado_servicio | VARCHAR(20) | no |  |
| fecha_creacion | DATETIME | no |  |
| fecha_actualizacion | DATETIME | no |  |

UNIQUE: `numero_documento`.

CHECK: `estado_servicio IN ('ACTIVO','RETIRADO','SUSPENDIDO','COMISION','LICENCIA')`.

CHECK: `numero_documento ~ '^[0-9]{6,10}$'`.

CHECK: `categoria IN ('OFICIAL','SUBOFICIAL','SOLDADO_PROFESIONAL','CIVIL')`.

### hoja_vida_artillero

| Columna | Tipo | NULL | Restricciones |
|---|---|---|---|
| id | CHAR(32) | no | PK |
| personal_militar_id | CHAR(32) | no | FK -> personal_militar.id |
| especialidad | VARCHAR(100) | si |  |
| fecha_ingreso_arma | DATE | si |  |
| observaciones | TEXT | si |  |
| fecha_creacion | DATETIME | no |  |
| fecha_actualizacion | DATETIME | no |  |

### roles

| Columna | Tipo | NULL | Restricciones |
|---|---|---|---|
| id | CHAR(32) | no | PK |
| codigo | VARCHAR(30) | no |  |
| nombre | VARCHAR(100) | no |  |
| activo | BOOLEAN | no |  |
| fecha_creacion | DATETIME | no |  |
| fecha_actualizacion | DATETIME | no |  |

UNIQUE: `codigo`.

CHECK: `codigo IN ('ADMINISTRADOR', 'USUARIO')`.

### permisos

| Columna | Tipo | NULL | Restricciones |
|---|---|---|---|
| id | CHAR(32) | no | PK |
| codigo | VARCHAR(50) | no |  |
| descripcion | VARCHAR(200) | no |  |
| fecha_creacion | DATETIME | no |  |
| fecha_actualizacion | DATETIME | no |  |

UNIQUE: `codigo`.

### roles_permisos

| Columna | Tipo | NULL | Restricciones |
|---|---|---|---|
| rol_id | CHAR(32) | no | PK; FK -> roles.id |
| permiso_id | CHAR(32) | no | PK; FK -> permisos.id |
| fecha_creacion | DATETIME | no |  |
| fecha_actualizacion | DATETIME | no |  |

### usuarios

| Columna | Tipo | NULL | Restricciones |
|---|---|---|---|
| id | CHAR(32) | no | PK |
| nombre_usuario | VARCHAR(60) | no |  |
| nombre_completo | VARCHAR(200) | no |  |
| hash_contrasena | VARCHAR(100) | no |  |
| rol_id | CHAR(32) | no | FK -> roles.id |
| activo | BOOLEAN | no |  |
| intentos_fallidos_consecutivos | INTEGER | no |  |
| bloqueado_hasta | DATETIME | si |  |
| fecha_ultimo_acceso | DATETIME | si |  |
| fecha_creacion | DATETIME | no |  |
| fecha_actualizacion | DATETIME | no |  |

### intentos_inicio_sesion

| Columna | Tipo | NULL | Restricciones |
|---|---|---|---|
| id | BIGINT | no | PK |
| nombre_usuario_intentado | VARCHAR(60) | no |  |
| usuario_id | CHAR(32) | si | FK -> usuarios.id |
| direccion_ip | INET | si |  |
| exitoso | BOOLEAN | no |  |
| motivo_fallo | VARCHAR(40) | si |  |
| fecha | DATETIME | no |  |

### sesiones_usuario

| Columna | Tipo | NULL | Restricciones |
|---|---|---|---|
| id | CHAR(32) | no | PK |
| usuario_id | CHAR(32) | no | FK -> usuarios.id |
| fecha_inicio | DATETIME | no |  |
| fecha_ultima_actividad | DATETIME | no |  |
| direccion_ip | INET | si |  |
| agente_usuario | VARCHAR(300) | si |  |
| revocada | BOOLEAN | no |  |
| fecha_revocacion | DATETIME | si |  |

### importaciones_excel

| Columna | Tipo | NULL | Restricciones |
|---|---|---|---|
| id | CHAR(32) | no | PK |
| usuario_id | CHAR(32) | no | FK -> usuarios.id |
| nombre_archivo | VARCHAR(255) | no |  |
| hash_sha256_archivo | CHAR(64) | no |  |
| fecha | DATETIME | no |  |
| filas_totales | INTEGER | no |  |
| filas_validas | INTEGER | no |  |
| filas_rechazadas | INTEGER | no |  |
| estado | VARCHAR(20) | no |  |
| errores | JSONB | si |  |
| fecha_creacion | DATETIME | no |  |
| fecha_actualizacion | DATETIME | no |  |

UNIQUE: `hash_sha256_archivo`.

CHECK: `estado IN ('PROCESANDO','APLICADA','RECHAZADA')`.

### auditoria_eventos

| Columna | Tipo | NULL | Restricciones |
|---|---|---|---|
| id | BIGINT | no | PK |
| fecha | DATETIME | no |  |
| usuario_id | CHAR(32) | si | FK -> usuarios.id |
| nombre_usuario | VARCHAR(60) | si |  |
| accion | VARCHAR(40) | no |  |
| numero_documento_consultado | VARCHAR(10) | si |  |
| resultado | VARCHAR(20) | si |  |
| direccion_ip | INET | si |  |
| agente_usuario | VARCHAR(300) | si |  |
| detalle | JSONB | si |  |

CHECK: `accion IN ('LOGIN_EXITOSO','LOGIN_FALLIDO','USUARIO_BLOQUEADO','USUARIO_DESBLOQUEADO','CONSULTA_ARTILLERO','CONSULTA_HABILITADOS','CONSULTA_NO_HABILITADOS','IMPORTACION_EXCEL','CIERRE_SESION')`.

### tipos_curso

| Columna | Tipo | NULL | Restricciones |
|---|---|---|---|
| id | CHAR(32) | no | PK |
| codigo | VARCHAR(30) | no |  |
| nombre | VARCHAR(200) | no |  |
| descripcion | TEXT | si |  |
| tipo_sistema | VARCHAR(50) | si |  |
| vigencia_meses | INTEGER | si |  |
| nota_minima_aprobacion | NUMERIC(4, 2) | si |  |
| activo | BOOLEAN | no |  |
| fecha_creacion | DATETIME | no |  |
| fecha_actualizacion | DATETIME | no |  |

CHECK: `nota_minima_aprobacion BETWEEN 0 AND 5`.

UNIQUE: `codigo`.

CHECK: `vigencia_meses > 0`.

### artillero_cursos

| Columna | Tipo | NULL | Restricciones |
|---|---|---|---|
| id | CHAR(32) | no | PK |
| hoja_vida_artillero_id | CHAR(32) | no | FK -> hoja_vida_artillero.id |
| tipo_curso_id | CHAR(32) | no | FK -> tipos_curso.id |
| numero_cohorte | VARCHAR(30) | si |  |
| fecha_inicio | DATE | si |  |
| fecha_fin | DATE | si |  |
| estado | VARCHAR(20) | no |  |
| nota_final | NUMERIC(4, 2) | si |  |
| numero_acta | VARCHAR(50) | si |  |
| institucion | VARCHAR(200) | si |  |
| importacion_excel_id | CHAR(32) | si | FK -> importaciones_excel.id |
| fecha_creacion | DATETIME | no |  |
| fecha_actualizacion | DATETIME | no |  |

CHECK: `nota_final BETWEEN 0 AND 5`.

CHECK: `estado IN ('EN_CURSO','APROBADO','REPROBADO','RETIRADO','ANULADO')`.

CHECK: `fecha_fin IS NULL OR fecha_inicio IS NULL OR fecha_fin >= fecha_inicio`.

UNIQUE: `hoja_vida_artillero_id, tipo_curso_id, numero_cohorte`.

### tipos_certificacion

| Columna | Tipo | NULL | Restricciones |
|---|---|---|---|
| id | CHAR(32) | no | PK |
| codigo | VARCHAR(30) | no |  |
| nombre | VARCHAR(200) | no |  |
| entidad_emisora | VARCHAR(200) | si |  |
| tipo_sistema | VARCHAR(50) | si |  |
| activo | BOOLEAN | no |  |
| fecha_creacion | DATETIME | no |  |
| fecha_actualizacion | DATETIME | no |  |

UNIQUE: `codigo`.

### artillero_certificaciones

| Columna | Tipo | NULL | Restricciones |
|---|---|---|---|
| id | CHAR(32) | no | PK |
| hoja_vida_artillero_id | CHAR(32) | no | FK -> hoja_vida_artillero.id |
| tipo_certificacion_id | CHAR(32) | no | FK -> tipos_certificacion.id |
| numero_certificado | VARCHAR(50) | si |  |
| fecha_expedicion | DATE | no |  |
| fecha_vencimiento | DATE | si |  |
| estado | VARCHAR(20) | no |  |
| importacion_excel_id | CHAR(32) | si | FK -> importaciones_excel.id |
| fecha_creacion | DATETIME | no |  |
| fecha_actualizacion | DATETIME | no |  |

CHECK: `fecha_vencimiento IS NULL OR fecha_vencimiento >= fecha_expedicion`.

CHECK: `estado IN ('ACTIVA','SUSPENDIDA','REVOCADA')`.

### sistemas_artilleria

| Columna | Tipo | NULL | Restricciones |
|---|---|---|---|
| id | CHAR(32) | no | PK |
| codigo | VARCHAR(30) | no |  |
| nombre | VARCHAR(200) | no |  |
| tipo_sistema | VARCHAR(50) | no |  |
| calibre_milimetros | NUMERIC(6, 2) | si |  |
| verificacion_habilitada | BOOLEAN | no |  |
| activo | BOOLEAN | no |  |
| fecha_creacion | DATETIME | no |  |
| fecha_actualizacion | DATETIME | no |  |

UNIQUE: `codigo`.

### requisitos_habilitacion

| Columna | Tipo | NULL | Restricciones |
|---|---|---|---|
| id | CHAR(32) | no | PK |
| sistema_artilleria_id | CHAR(32) | si | FK -> sistemas_artilleria.id |
| tipo_requisito | VARCHAR(20) | no |  |
| tipo_curso_id | CHAR(32) | si | FK -> tipos_curso.id |
| tipo_certificacion_id | CHAR(32) | si | FK -> tipos_certificacion.id |
| descripcion | VARCHAR(300) | no |  |
| activo | BOOLEAN | no |  |
| fecha_creacion | DATETIME | no |  |
| fecha_actualizacion | DATETIME | no |  |

CHECK: `tipo_requisito IN ('CURSO','CERTIFICACION')`.

CHECK: `(tipo_requisito = 'CURSO' AND tipo_curso_id IS NOT NULL AND tipo_certificacion_id IS NULL) OR (tipo_requisito = 'CERTIFICACION' AND tipo_certificacion_id IS NOT NULL AND tipo_curso_id IS NULL)`.

### tipos_cargo

| Columna | Tipo | NULL | Restricciones |
|---|---|---|---|
| id | CHAR(32) | no | PK |
| codigo | VARCHAR(30) | no |  |
| nombre | VARCHAR(200) | no |  |
| descripcion | TEXT | si |  |
| activo | BOOLEAN | no |  |
| fecha_creacion | DATETIME | no |  |
| fecha_actualizacion | DATETIME | no |  |

UNIQUE: `codigo`.

### artillero_cargos

| Columna | Tipo | NULL | Restricciones |
|---|---|---|---|
| id | CHAR(32) | no | PK |
| hoja_vida_artillero_id | CHAR(32) | no | FK -> hoja_vida_artillero.id |
| tipo_cargo_id | CHAR(32) | no | FK -> tipos_cargo.id |
| unidad_militar_id | CHAR(32) | si | FK -> unidades_militares.id |
| fecha_inicio | DATE | no |  |
| fecha_fin | DATE | si |  |
| numero_resolucion | VARCHAR(50) | si |  |
| observaciones | TEXT | si |  |
| fecha_creacion | DATETIME | no |  |
| fecha_actualizacion | DATETIME | no |  |

CHECK: `fecha_fin IS NULL OR fecha_fin >= fecha_inicio`.

### componentes

| Columna | Tipo | NULL | Restricciones |
|---|---|---|---|
| id | CHAR(32) | no | PK |
| codigo | VARCHAR(100) | no |  |
| nombre | VARCHAR(150) | no |  |
| ruta_angular | VARCHAR(250) | si |  |
| descripcion | TEXT | si |  |
| componente_padre_id | CHAR(32) | si | FK -> componentes.id |
| orden | INTEGER | no |  |
| activo | BOOLEAN | no |  |
| fecha_creacion | DATETIME | no |  |
| fecha_actualizacion | DATETIME | no |  |

UNIQUE: `codigo`.

### rol_permisos

| Columna | Tipo | NULL | Restricciones |
|---|---|---|---|
| rol_id | CHAR(32) | no | PK; FK -> roles.id |
| componente_id | CHAR(32) | no | PK; FK -> componentes.id |
| puede_acceder | BOOLEAN | no |  |
| puede_crear | BOOLEAN | no |  |
| puede_leer | BOOLEAN | no |  |
| puede_actualizar | BOOLEAN | no |  |
| puede_eliminar | BOOLEAN | no |  |
| fecha_creacion | DATETIME | no |  |
| fecha_actualizacion | DATETIME | no |  |

CHECK: `puede_acceder OR NOT (puede_crear OR puede_leer OR puede_actualizar OR puede_eliminar)`.

### usuario_permisos

| Columna | Tipo | NULL | Restricciones |
|---|---|---|---|
| usuario_id | CHAR(32) | no | PK; FK -> usuarios.id |
| componente_id | CHAR(32) | no | PK; FK -> componentes.id |
| puede_acceder | BOOLEAN | no |  |
| puede_crear | BOOLEAN | no |  |
| puede_leer | BOOLEAN | no |  |
| puede_actualizar | BOOLEAN | no |  |
| puede_eliminar | BOOLEAN | no |  |
| actualizado_por_id | CHAR(32) | si | FK -> usuarios.id |
| fecha_creacion | DATETIME | no |  |
| fecha_actualizacion | DATETIME | no |  |

CHECK: `puede_acceder OR NOT (puede_crear OR puede_leer OR puede_actualizar OR puede_eliminar)`.

## Verificacion y aprobacion

Antes de cambios: Python 3.12.10; pip check correcto; 58 pruebas aprobadas y una
integracion omitida por defecto. No se mostraron credenciales.
Los contratos aprobados no se editan unilateralmente. La propuesta modifica el
modelo actual de forma aditiva, preservando el archivo de migracion 0001.
Las pruebas de migracion online, seeds y reversion quedan optativas y pendientes
hasta aprobacion expresa. Las pruebas offline no abren conexiones.

Solicitar aprobacion final de este documento y del DDL preparado antes de ejecutar.
