# Aplicación Angular ESART

Angular 22.2.x con TypeScript 6.0.x; Angular CLI del proyecto y lockfile incluidos. No se requiere instalar globalmente una CLI diferente. Usar npm ci para reproducir dependencias.

```powershell
npm ci
npm start
npm run build
npm test -- --watch=false
```

Pantalla /unidades, servicio relativo /api/catalogos/unidades, proxy local a 127.0.0.1:8081. Build en dist/esart. Los BIGINT llegan como cadenas y se conservan sin Number/parseInt.

El inicio de sesión y la visualización autenticada no están completados. Las pruebas de transporte usan HttpTestingController; no consultan PostgreSQL. Ver [guía del frontend](../README.md), [configuración general](../../README.md) y [estado técnico](../../docs/ESART_ESTADO_DESARROLLO.md).
