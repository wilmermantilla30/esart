# Frontend ESART

El proyecto Angular **ya existe** en [esart/](esart/). No es una carpeta reservada. Desde frontend/esart:

```powershell
npm ci
npm start
npm run build
npm test -- --watch=false
```

Abrir http://localhost:4200/unidades. npm start usa proxy.conf.json: /api hacia http://127.0.0.1:8081. Las cookies y rutas relativas mantienen el mismo origen en desarrollo. El build genera esart/dist/esart; su publicación/servicio estático desde FastAPI es trabajo pendiente, no comportamiento ya implementado.

La interfaz usa UnidadesService/HttpClient, identificadores string, búsqueda por código/nombre, filtro por tipo/pendiente y actividad, superior y ruta jerárquica. Incluye carga, errores y reintento; no contiene arrays institucionales simulados. app.config.ts configura CSRF según contrato.

Faltan proveedor de identidad, login/guardas, integración de negocio y validación visual autenticada. Un 401 no se evita con datos ficticios. Los nombres nucleo/compartido/paginas describían una arquitectura propuesta anterior; la implementación actual está en src/app/unidades.ts y unidades.service.ts.

Consultar [README general](../README.md), [estado](../docs/ESART_ESTADO_DESARROLLO.md) y [contrato API](../docs/contrato_api.md). No presentar la compilación o el test HTTP en memoria como una prueba visual con datos reales.

## Inicio de sesión (HU-18)

Rutas: `/inicio-sesion` (solo sin sesión), `/inicio` (provisional, con sesión) y `/unidades` (con sesión).
Diseño: plantilla institucional de Stitch, traducida a Angular con Tailwind compilado localmente.

```
src/app/
├── nucleo/
│   ├── modelos/        # sesion.ts (contrato §2), error-api.ts (formato único de error)
│   ├── servicios/      # cliente-api.service.ts (único acceso a /api), sesion.service.ts
│   ├── interceptores/  # sesion-expirada: 401 -> login con aviso de inactividad
│   ├── guardas/        # exigirSesion, soloSinSesion
│   └── rutas-paginas.ts
├── compartido/         # encabezado y pie institucionales
└── paginas/            # inicio-sesion/, inicio/
```

Reglas aplicadas:

- **Sin CDN:** Tailwind 4 (`@tailwindcss/postcss`, `.postcssrc.json`), fuentes `@fontsource/*` e íconos
  `material-symbols` salen de `node_modules` y viajan en el build. Los tokens del diseño están en `src/styles.css` (`@theme`).
- **Sin estilos en línea:** `inlineCritical` desactivado en producción; sin `innerHTML` ni `bypassSecurityTrust`.
- **Sesión:** el token vive solo en la cookie httpOnly. El front guarda en memoria los datos públicos del
  usuario y los recupera con `/api/auth/yo` al recargar. No usa localStorage.
- **Errores:** todo error pasa por `leerErrorApi`; nunca se muestran detalles técnicos.
- El escudo está en `public/imagenes/escudo-esart.png`. La foto de la Escuela se agregará después.

Pendiente del backend: `POST /api/auth/login`, `GET /api/auth/yo` y `POST /api/auth/cerrar-sesion`
sobre el modelo de HU-04. El captcha (HU-07) se agrega cuando exista `GET /api/auth/captcha`.
