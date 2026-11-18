# Registro manual de personal militar

Pestaña **Personal militar → Registro manual** (`/personal/cargue-manual`), componente de la malla
`PERSONAL_CARGUE_MANUAL`. Registra un efectivo en `esart.personal_militar` desde un formulario,
sin Excel.

## 1. Flujo en pantalla

1. El formulario pide los catálogos (`GET /api/personal/opciones-registro`) y preselecciona la
   unidad `ESART` si existe.
2. Campos:

   | Campo | Obligatorio | Regla |
   |---|---|---|
   | Documento de identidad | Sí | Solo dígitos, 5 a 15. Único en `personal_militar`. |
   | Nombres / Apellidos | Sí | Máximo 150; se quitan espacios repetidos. |
   | Grado militar | Sí | Sigla del catálogo, agrupada por categoría. Elegir el grado fija la categoría. |
   | Género | Sí | `M` o `F`. |
   | Categoría | Sí | `OFICIAL`, `SUBOFICIAL` o `SOLDADO_PROFESIONAL`. Si se cambia y el grado no le pertenece, el grado se borra. |
   | Unidad militar asignada | No | Unidad activa de `esart_ref.unidades_militares`. |
   | Especialidad en artillería | No | Máximo 100. |
   | Estado del efectivo | Sí (por defecto activo) | Interruptor → `personal_militar.activo`. |

3. **Registrar Militar** envía `POST /api/personal`. Con éxito, el formulario se reemplaza por el
   resumen del registro y los accesos:

   | Botón | Destino | Visible si el usuario tiene |
   |---|---|---|
   | Registrar como instructor | `/instructores?cedula=<documento>` | operación *crear* en `INSTRUCTORES` |
   | Crear usuario del sistema | `/administracion/usuarios?cedula=<documento>` | operación *crear* en `USUARIOS` |

   Las páginas destino leen `cedula`, abren su formulario de alta y buscan al militar
   automáticamente (solo si el usuario puede crear allí). Además tienen su guarda de ruta y el
   backend vuelve a verificar el permiso en cada petición: ocultar el botón es solo comodidad.

4. **Registrar otro** limpia el formulario; **Cancelar / Volver al panel** lleva a `/personal`.

## 2. API

Ambas rutas exigen sesión, CSRF (en el POST) y la operación **crear** de `PERSONAL_CARGUE_MANUAL`
(resuelta en PostgreSQL en cada petición). Sin permiso: `403`.

### `GET /api/personal/opciones-registro`

```json
{
  "categorias": [
    { "codigo": "OFICIAL", "nombre": "Oficial", "grados": [{ "codigo": "MY", "nombre": "Mayor" }] }
  ],
  "unidades": [{ "id": 7, "codigo": "ESART", "nombre": "Escuela de Artillería" }]
}
```

### `POST /api/personal`

```json
{
  "documento_identidad": "1024589632",
  "nombres": "Carlos Andrés",
  "apellidos": "Colorado Gil",
  "grado": "MY",
  "genero": "M",
  "categoria": "OFICIAL",
  "unidad_actual_id": 7,
  "especialidad_actual": null,
  "activo": true
}
```

| Respuesta | Cuándo |
|---|---|
| `201` + registro (`id`, `nombre_completo`, `unidad_nombre`, …) | Guardado y auditado. |
| `409 DOCUMENTO_EXISTENTE` | La cédula ya está en `personal_militar`. |
| `422 DATOS_INVALIDOS` | Formato, grado fuera de la categoría, unidad inexistente o inactiva. |
| `503 REGISTRO_NO_DISPONIBLE` | Falta la migración p0015 (no se guarda nada). |

## 3. Catálogo de grados

Definido en `backend/aplicacion/servicios/registro_personal.py` (`GRADOS_POR_CATEGORIA`); se
guarda la sigla en `personal_militar.grado`:

- **Oficial:** ST, TE, CT, MY, TC, CR, BG, MG, GR.
- **Suboficial:** C3, CS, CP, SS, SV, SP, SM, SMC, SMCC.
- **Soldado profesional:** SLP.

Para agregar o cambiar grados basta con editar ese diccionario: el formulario lo toma del backend.
Pendiente: confirmar el catálogo oficial con la Escuela (ver `contrato_esquema_bd.md` §10).

## 4. Base de datos

- No crea tablas ni privilegios nuevos: usa el `INSERT` por columnas sobre `esart.personal_militar`
  que la cuenta `esart_aplicacion` ya tiene desde p0011 (cargue por Excel).
- **Migración `p0015_registro_manual_personal`:** agrega la acción `PERSONAL_REGISTRADO` al CHECK
  de `esart.auditoria_eventos`. SQL equivalente para ejecutar a mano como `postgres`:
  `backend/propuestas/p0015_registro_manual_personal.sql`.
- Cada registro deja un evento `PERSONAL_REGISTRADO` con el usuario, la IP, la cédula registrada
  y el detalle (`personal_id`, `grado`, `categoria`, `unidad_actual_id`, `activo`). El registro y su
  auditoría se confirman en la misma transacción: o quedan ambos o ninguno.

## 5. Archivos

| Capa | Archivo |
|---|---|
| Servicio | `backend/aplicacion/servicios/registro_personal.py` |
| Ruta | `backend/aplicacion/rutas/personal.py` |
| Esquemas | `backend/aplicacion/esquemas/personal.py` |
| Migración | `backend/migraciones_principal/versions/p0015_registro_manual_personal.py` |
| Pruebas backend | `backend/pruebas/test_registro_personal.py` |
| Componente | `frontend/esart/src/app/paginas/personal-militar/cargue-manual/` |
| Servicio front | `frontend/esart/src/app/nucleo/servicios/registro-personal.service.ts` |
| Modelos front | `frontend/esart/src/app/nucleo/modelos/personal.ts` |
| Accesos `?cedula=` | `paginas/instructores/instructores.ts`, `paginas/administracion/gestion-usuarios/gestion-usuarios.ts` |
