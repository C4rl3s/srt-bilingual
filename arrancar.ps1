# Arranca la app en desarrollo: backend (:8000) y frontend (:5173), cada uno en su
# propia ventana de PowerShell, y abre el navegador cuando la interfaz responde.
# Para pararla, cierra las dos ventanas (o Ctrl+C en cada una).
#
# Uso: doble clic en arrancar.cmd, o desde PowerShell: .\arrancar.ps1

$ErrorActionPreference = 'Stop'
$raiz = $PSScriptRoot

# uv y Node se instalaron con winget: si esta sesión no los ve, se recarga el PATH.
$env:Path = [Environment]::GetEnvironmentVariable('Path', 'Machine') + ';' +
            [Environment]::GetEnvironmentVariable('Path', 'User')

function Escuchando([int]$puerto) {
    [bool](Get-NetTCPConnection -State Listen -LocalPort $puerto -ErrorAction SilentlyContinue)
}

# --- Backend ---
if (Escuchando 8000) {
    Write-Host 'El backend ya está en marcha (puerto 8000).'
} else {
    Write-Host 'Aplicando migraciones de la base de datos...'
    Push-Location "$raiz\backend"
    try { uv run alembic upgrade head } finally { Pop-Location }
    if ($LASTEXITCODE -ne 0) { throw 'Falló alembic upgrade head' }

    # Solo en 127.0.0.1: /fs/browse deja navegar el disco (ver README).
    Start-Process powershell -WorkingDirectory "$raiz\backend" -ArgumentList @(
        '-NoExit', '-Command',
        "`$Host.UI.RawUI.WindowTitle = 'srt-bilingual: backend'; `$env:Path = '$env:Path'; " +
        'uv run uvicorn app.main:app --reload --host 127.0.0.1 --port 8000'
    )
}

# --- Frontend ---
if (Escuchando 5173) {
    Write-Host 'El frontend ya está en marcha (puerto 5173).'
} else {
    if (-not (Test-Path "$raiz\frontend\node_modules")) {
        Write-Host 'Instalando dependencias del frontend (solo la primera vez)...'
        Push-Location "$raiz\frontend"
        try { npm install } finally { Pop-Location }
    }
    Start-Process powershell -WorkingDirectory "$raiz\frontend" -ArgumentList @(
        '-NoExit', '-Command',
        "`$Host.UI.RawUI.WindowTitle = 'srt-bilingual: frontend'; `$env:Path = '$env:Path'; " +
        'npm run dev'
    )
}

# --- Navegador ---
Write-Host 'Esperando a que responda la interfaz...'
$limite = (Get-Date).AddSeconds(60)
while (-not ((Escuchando 8000) -and (Escuchando 5173))) {
    if ((Get-Date) -gt $limite) {
        throw 'La app no arrancó en 60 s: mira los errores en las ventanas del backend y el frontend.'
    }
    Start-Sleep -Milliseconds 500
}
Start-Process 'http://localhost:5173'
Write-Host 'Listo: http://localhost:5173'
