# Documentos PDF del artillero (ReportLab)

Desde **Personal militar → Verificar artillero**, en la ficha del militar verificado, hay un
selector con tres documentos y el botón **Generar documento**. El backend arma el PDF con
ReportLab y el navegador lo descarga.

| Opción | Documento | Cuándo se puede generar |
|---|---|---|
| `DIPLOMA` | Diploma del curso aprobado más reciente (hoja horizontal, marco dorado). | Solo si el artillero tiene al menos un curso aprobado; si no, 409. |
| `OFICIO_REMISORIO` | Oficio de la Escuela al Comandante de la unidad que remite el resultado APTO / NO APTO, con motivos y anexos. | Siempre. |
| `CERTIFICACION` | Certificación de habilitación: resultado destacado, datos del artillero, criterios, cursos y reentrenamientos. | Siempre. |

## 1. Estructura en el backend (`backend/aplicacion/reportes/`)

| Archivo | Qué hace |
|---|---|
| `maestro.py` | **Script maestro.** `generar_documento(opcion, datos)` recibe la opción, busca su script en `REPORTES` y devuelve `(pdf_bytes, nombre_archivo)`. También funciona por consola. |
| `diploma.py` | Script del diploma (`generar(datos)`); `curso_del_diploma` elige el curso. |
| `oficio_remisorio.py` | Script del oficio remisorio. |
| `certificacion.py` | Script de la certificación. |
| `comun.py` | `DatosDocumento` (datos de entrada), estilos, tablas, membrete, pie, firma y textos institucionales. |

Los scripts **no consultan la base de datos**: reciben un `DatosDocumento`. La consulta, el permiso
y la auditoría están en la ruta (`rutas/verificacion.py`). Por eso se pueden probar y generar sin
PostgreSQL.

### Agregar un documento nuevo

1. Crear `aplicacion/reportes/<nombre>.py` con `generar(datos: DatosDocumento) -> bytes`
   (usar `construir_pdf`, `estilos`, `tabla` y `bloque_firma` de `comun.py`).
2. Registrarlo en `REPORTES` de `maestro.py`.
3. Agregarlo al tipo `OpcionDocumento` de `rutas/verificacion.py` y a `DOCUMENTOS_ARTILLERO` del
   front (`nucleo/modelos/verificacion.ts`).

### Cambiar textos institucionales

Nombre de la escuela, lema, ciudad y firmante están en las constantes al inicio de `comun.py`
(`INSTITUCION`, `ESCUELA`, `ESCUELA_TEXTO`, `LEMA`, `CIUDAD`, `FIRMANTE_NOMBRE`, `FIRMANTE_CARGO`).

### Probar por consola (datos ficticios, sin base de datos)

```powershell
cd backend
.venv\Scripts\python.exe -m aplicacion.reportes.maestro DIPLOMA ejemplo_diploma.pdf
.venv\Scripts\python.exe -m aplicacion.reportes.maestro OFICIO_REMISORIO ejemplo_oficio.pdf
.venv\Scripts\python.exe -m aplicacion.reportes.maestro CERTIFICACION ejemplo_certificacion.pdf
```

## 2. API

### `GET /api/verificar/documentos`
Lista de opciones para el selector: `[{ "codigo": "DIPLOMA", "nombre": "Diploma" }, …]`.

### `GET /api/verificar/artillero/{cedula}/documento?tipo=<OPCION>`

- Permiso: `PERSONAL_VERIFICAR` (leer), igual que verificar.
- Respuesta 200: `application/pdf` con
  `Content-Disposition: attachment; filename*=UTF-8''<opcion>_<cedula>.pdf` y `Cache-Control: no-store`.
- La cédula del PDF (y del nombre del archivo) sale **enmascarada** si el usuario no tiene
  `VER_DOCUMENTO_COMPLETO`, con la misma regla de la verificación.
- Errores: **404** `ARTILLERO_NO_ENCONTRADO`, **409** `DOCUMENTO_NO_DISPONIBLE` (diploma sin curso
  aprobado), **422** opción inválida.
- Auditoría: evento `CONSULTA_ARTILLERO` con `resultado = DOC_<OPCION>` y
  `detalle = { documento_generado, numero }`. No requiere migración.
- Número del documento: `ESART-AAAAMMDD-XXXXXX` (fecha + sufijo aleatorio). Aparece en el PDF y en
  la auditoría para rastrear quién lo generó y cuándo.

## 3. Front

- `paginas/personal-militar/verificar-artillero`: selector (`#tipo-documento`) y botón
  **Generar documento** en la ficha. Usa la cédula tal como se consultó (la de la ficha puede venir
  enmascarada).
- `nucleo/servicios/verificacion.service.ts` → `generarDocumento(cedula, tipo)`: descarga el
  Blob; si el backend responde error, convierte el cuerpo (que llega como Blob) a JSON para mostrar
  el mensaje real.

## 4. Dependencia

`reportlab==5.1.0` (en `backend/requirements.txt`). Instalar con:

```powershell
cd backend
.venv\Scripts\python.exe -m pip install -r requirements.txt
```

## 5. Pruebas

- `backend/pruebas/test_documentos_artillero.py`:
  - cada opción genera un PDF de una página;
  - opción desconocida;
  - diploma sin curso aprobado;
  - textos con `<` y `&`;
  - nombre de archivo con cédula enmascarada;
  - certificación de varias páginas;
  - línea de comandos;
  - la ruta con dependencias simuladas;
  - integración con PostgreSQL (se omite si no hay `ESART_URL_BD_INTEGRACION`).
- `verificar-artillero.spec.ts`: opciones del selector, descarga y mensaje de error 409.

## 6. Pendientes para validar con la Escuela

- Nombre real del firmante (hoy "Director de la Escuela de Artillería") y si se agrega el escudo.
- Formato oficial del número de oficio (hoy `ESART-AAAAMMDD-XXXXXX`).
