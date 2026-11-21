"""Firma desde el celular: permisos de la API sobre la cadena de firma heredada (sin DDL).

p0018 dejó la estructura (documentos, solicitudes, consentimientos, firmas, desafíos) pero solo dio
a la API lo necesario para guardar PDF. El flujo QR → rúbrica → TOTP → PDF firmado necesita además:
- solicitudes_firma: crear la solicitud y cambiar su estado (abierta, aprobada, expirada).
- autorizaciones_firmantes: leer firmantes vigentes; el administrador concede y revoca.
- consentimientos_firma, desafios_autenticacion, firmas_certificado: registrar la evidencia de la firma
  (solo INSERT/SELECT: consentimientos y firmas son inmutables por trigger).
No crea tablas ni toca datos. El downgrade revoca exactamente lo concedido.
"""

from alembic import op

revision = "p0019_firma_movil"
down_revision = "p0018_firma_documental"
branch_labels = None
depends_on = None

CUENTA = "esart_aplicacion"
CONCESIONES = (
    "GRANT SELECT, INSERT ON esart_firma.solicitudes_firma TO {c}",
    "GRANT UPDATE (estado, abierta_en, decidida_en, motivo_rechazo) ON esart_firma.solicitudes_firma TO {c}",
    "GRANT SELECT, INSERT ON esart_firma.autorizaciones_firmantes TO {c}",
    "GRANT UPDATE (revocado_en) ON esart_firma.autorizaciones_firmantes TO {c}",
    "GRANT SELECT, INSERT ON esart_firma.consentimientos_firma TO {c}",
    "GRANT SELECT, INSERT ON esart_firma.desafios_autenticacion TO {c}",
    "GRANT SELECT, INSERT ON esart_firma.firmas_certificado TO {c}",
)
REVOCACIONES = (
    "REVOKE SELECT, INSERT ON esart_firma.solicitudes_firma FROM {c}",
    "REVOKE UPDATE (estado, abierta_en, decidida_en, motivo_rechazo) ON esart_firma.solicitudes_firma FROM {c}",
    "REVOKE SELECT, INSERT ON esart_firma.autorizaciones_firmantes FROM {c}",
    "REVOKE UPDATE (revocado_en) ON esart_firma.autorizaciones_firmantes FROM {c}",
    "REVOKE SELECT, INSERT ON esart_firma.consentimientos_firma FROM {c}",
    "REVOKE SELECT, INSERT ON esart_firma.desafios_autenticacion FROM {c}",
    "REVOKE SELECT, INSERT ON esart_firma.firmas_certificado FROM {c}",
)


def _aplicar(sentencias):
    cuerpo = "\n".join(f"    {s.format(c=CUENTA)};" for s in sentencias)
    op.execute(f"""
        DO $$ BEGIN
          IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{CUENTA}') THEN
{cuerpo}
          END IF;
        END $$
    """)  # noqa: S608


def upgrade():
    _aplicar(CONCESIONES)


def downgrade():
    _aplicar(REVOCACIONES)
