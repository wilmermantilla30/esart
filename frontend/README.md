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
