# Autenticador integrado en el menú de seguridad

Fecha: 16 de noviembre de 2026.

La llave del encabezado abre un desplegable con cambio de contraseña y configuración/administración del autenticador. Cerrar sesión permanece en su botón existente. El panel principal ya no incluye el acceso independiente CONFIGURAR AUTENTICADOR; /totp se conserva como ruta protegida por compatibilidad.

MenuSeguridad consulta TotpService.estado() al abrir. No solicita QR ni secreto al consultar. Abre el componente Totp existente como diálogo, con volverAlInicioAlCerrar=false: cerrar conserva la página actual y vuelve a consultar el estado. Se reutilizan validación, recuperación, revocación, confirmación de contraseña y códigos, así como limpieza del secreto al activar/cerrar. El usuario debe confirmar contraseña para obtener o recuperar el QR pendiente. No se creó un segundo flujo ni nuevos endpoints.

El GET existente /api/auth/totp/estado añade únicamente estado, necesario para distinguir PENDIENTE de REVOCADO: los booleanos anteriores no distinguían esos casos. No devuelve secretos ni cambia las dependencias de autorización. NO_CONFIGURADO muestra configuración; PENDIENTE muestra completar; ACTIVO muestra administración; REVOCADO permite iniciar configuración. Si el backend comunica BLOQUEADO se muestra la limitación sin inventar una recuperación; ante error se permite reconsultar, sin revelar detalles internos. Las operaciones existentes siguen sujetas a contraseña, factor, sesión y controles del backend.

Diseño: desplegable anclado, SVG oficiales Lucide locales con licencia incluida en public/iconos/lucide/LICENSE, colores azules, estado visual, ancho adaptable y movimiento reducido. Se conserva el diálogo institucional. Accesibilidad: botón con aria-expanded, estado anunciado, Escape/clic exterior, navegación por flechas/Home/End y foco del diálogo existente.

Verificación: 111 pruebas Angular aprobadas en 19 archivos (7 nuevas del menú); 41 pruebas unitarias TOTP backend aprobadas, incluyendo cuatro estados del endpoint sin secretos ni commit. Ruff y build Angular aprobados. Persisten las advertencias existentes por presupuesto CSS de Totp (6.64 kB frente a 4 kB) y qrcode CommonJS. No se efectuó una nueva prueba integrada contra PostgreSQL o aplicaciones autenticadoras reales; las pruebas HTTP usan dobles de prueba.

No se modificaron CAPTCHA, contadores, bloqueo, JWT/cookies, cambio obligatorio de contraseña, permisos ni migraciones. No hubo escrituras PostgreSQL, commits ni push. El stash se conserva.
