# Frontend de ESART (Angular)

Dashboard del comandante, construido en **Angular** con TypeScript.

> **Estado:** carpeta reservada. El proyecto Angular se genera aquí (historia FE-01) con la
> misma versión de Angular que usa Vulcano, para que la integración posterior sea directa.

Todo lo que el front pide al backend está definido en
[docs/contrato_api.md](../docs/contrato_api.md). Si algo no está en el contrato, se agrega primero
al contrato (por Pull Request) y después se programa.

---

## Cómo trabaja con el backend

| Momento | Cómo llega el front al navegador | Cómo llega a la API |
|---|---|---|
| **Desarrollo** | `ng serve` en <http://localhost:4200> | `proxy.conf.json` redirige `/api` a <http://127.0.0.1:8081>. Para el navegador todo es el mismo origen, así la cookie de sesión funciona sin CORS |
| **Producción** | `ng build` genera `dist/`; FastAPI sirve esos archivos (historia HU-21) | Mismo servidor, mismo origen. **No hace falta Node.js en el servidor** |

---

## Estructura propuesta dentro de `src/app/`

```
src/app/
├── nucleo/                 # Servicios únicos de toda la aplicación (se crean una sola vez)
│   ├── servicios/          # cliente-api.service.ts (ÚNICO acceso al backend), sesion.service.ts
│   ├── interceptores/      # manejo-errores.interceptor.ts (formato único de error del contrato)
│   ├── guardas/            # sesion-activa.guard.ts, permiso.guard.ts
│   └── modelos/            # Interfaces TypeScript que copian las respuestas del contrato de API
├── compartido/             # Componentes reutilizables: tabla-paginada, tarjeta-resultado, alerta, cargando
├── paginas/                # Una carpeta por pantalla
│   ├── inicio-sesion/
│   ├── verificacion/
│   ├── habilitacion/       # Listados de habilitados / no habilitados
│   └── importacion/
└── datos-simulados/        # Interceptor + JSON de ejemplo para trabajar sin backend (solo desarrollo)
```

Nombres de archivos en `kebab-case` según la convención de Angular; nombres de clases, métodos,
variables y comentarios en **español descriptivo**, igual que en el backend.

---

## Reglas del front

1. **Nada desde internet.** Ni CDN ni Google Fonts: tipografías e íconos dentro del proyecto
   (`src/assets` o `public/`). El servidor puede estar en una red sin internet.
2. **Un solo acceso a la API:** `ClienteApiService`. Ningún componente usa `HttpClient` directamente.
   Así el manejo de sesión, CSRF y errores es igual en todo el sistema.
3. **El front nunca toca el token.** La sesión va en una cookie `httpOnly`. La protección CSRF usa
   el soporte propio de Angular (`withXsrfConfiguration`), ver contrato §1.1.
4. **Errores centralizados** en un interceptor que traduce los códigos del contrato
   (`SESION_EXPIRADA` → ir a inicio de sesión, `SIN_PERMISO`, `USUARIO_BLOQUEADO`, …).
5. **Rutas protegidas con guardas** según sesión y permisos (`/api/auth/yo`).
   Ocultar una opción no reemplaza la validación del backend.
6. **Sin `innerHTML` con datos de la API** ni `bypassSecurityTrust*`: se usa la interpolación de
   Angular, que escapa el contenido.
7. **Compatible con la CSP del servidor:** sin estilos ni scripts en línea en la versión compilada
   (desactivar `inlineCritical` en `angular.json`).
8. **No guardar datos de artilleros** en `localStorage` ni `sessionStorage`. Al cerrar sesión se
   limpia el estado.
9. **Nada de `console.log`** con respuestas, cédulas o datos personales.
10. **Reutilizar antes de crear:** si un componente o servicio ya existe en `nucleo/` o
    `compartido/`, se usa ese.

---

## Comandos (cuando el proyecto esté generado)

```powershell
npm install
npm start          # ng serve con proxy hacia el backend
npm run build      # compilación de producción en dist/
npm test
```
