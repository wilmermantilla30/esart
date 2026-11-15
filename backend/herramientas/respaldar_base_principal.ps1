# Ejecutar manualmente con una cuenta de respaldo que pueda leer los esquemas.
# No cambia permisos, configuración de la aplicación ni registros de PostgreSQL.
param(
    [Parameter(Mandatory = $true)][string]$Servidor,
    [Parameter(Mandatory = $true)][string]$UsuarioRespaldo,
    [Parameter(Mandatory = $true)][string]$DirectorioSalida,
    [int]$Puerto = 5432
)
$ErrorActionPreference = 'Stop'
$binariosPostgres = 'C:\Program Files\PostgreSQL\18\bin'
$opcionesPrevias = $env:PGOPTIONS
try {
    $env:PGOPTIONS = '-c default_transaction_read_only=on'
    $identidad = & "$binariosPostgres\psql.exe" -X -h $Servidor -p $Puerto -U $UsuarioRespaldo `
        -d esart_db -W -t -A -v ON_ERROR_STOP=1 -c 'SELECT current_database()'
    if ($LASTEXITCODE -ne 0 -or $identidad.Trim() -ne 'esart_db') {
        throw 'No se confirmó esart_db; no se inicia el respaldo.'
    }
    if (Test-Path -LiteralPath $DirectorioSalida) {
        throw 'Usar un directorio nuevo para no sobrescribir evidencias.'
    }
    $carpetaRespaldo = New-Item -ItemType Directory -Path $DirectorioSalida
    $archivoRespaldo = Join-Path $carpetaRespaldo.FullName 'esart_db_completo.dump'
    & "$binariosPostgres\pg_dump.exe" -h $Servidor -p $Puerto -U $UsuarioRespaldo -d esart_db -W `
        --format=custom --create --file=$archivoRespaldo
    if ($LASTEXITCODE -ne 0) { throw 'Respaldo fallido: el archivo parcial NO es válido.' }
    & "$binariosPostgres\pg_restore.exe" --list $archivoRespaldo |
        Set-Content -LiteralPath (Join-Path $carpetaRespaldo.FullName 'contenido.txt') -Encoding utf8
    if ($LASTEXITCODE -ne 0) { throw 'Archivo ilegible; no aprobar respaldo.' }
    $sqlDecodificado = Join-Path $carpetaRespaldo.FullName 'restauracion_decodificada.sql'
    & "$binariosPostgres\pg_restore.exe" --file=$sqlDecodificado $archivoRespaldo
    if ($LASTEXITCODE -ne 0) { throw 'No se decodificó el respaldo completo.' }
    Get-FileHash -LiteralPath $archivoRespaldo -Algorithm SHA256
    Write-Output 'Respaldo generado y decodificado. Falta restauración real en un destino nuevo independiente.'
} finally {
    $env:PGOPTIONS = $opcionesPrevias
}
