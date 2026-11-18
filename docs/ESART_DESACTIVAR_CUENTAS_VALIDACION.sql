-- Solo cuentas exclusivas de validacion; ejecutar como propietario al finalizar las pruebas.
BEGIN;
UPDATE esart_ref.usuarios SET activo=false WHERE id=4 AND usuario='mfa.validacion.032957fbe274467b9164d4830c80d1c3';
UPDATE esart_ref.usuarios SET activo=false WHERE id=5 AND usuario='mfa.validacion.140dccc754884865b2923df3530ba4f7';
UPDATE esart_ref.usuarios SET activo=false WHERE id=6 AND usuario='mfa.validacion.e4f8b545301244d592f0af361db6eb4b';
UPDATE esart_ref.usuarios SET activo=false WHERE id=7 AND usuario='mfa.validacion.42832672f402458eb202854146c247e6';
COMMIT;
