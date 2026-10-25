# Configuración inicial en Windows (PowerShell), desde la raíz del repo:
#   powershell -ExecutionPolicy Bypass -File scripts\setup.ps1
$ErrorActionPreference = "Stop"

git config core.hooksPath .githooks
Write-Host "OK  hooks anti-fuga activados (.githooks)"

# Limpia los outputs de los notebooks automáticamente al hacer git add (si nbstripout está instalado)
if (Get-Command nbstripout -ErrorAction SilentlyContinue) {
    nbstripout --install
    Write-Host "OK  nbstripout activado: los notebooks se guardan en git sin outputs"
} else {
    Write-Host "--  nbstripout no está instalado (pip install -r requirements.txt); el hook igual bloquea outputs"
}

if (-not (Test-Path ".env")) {
    Copy-Item ".env.example" ".env"
    Write-Host "OK  .env creado desde .env.example  -> llénalo con TUS credenciales (no se sube)"
}

python scripts/check_no_data.py --all
Write-Host ""
Write-Host "Siguiente paso: crea tu carpeta de datos FUERA del repo y ponla en DATA_DIR dentro de .env"
Write-Host "Recomendado: una carpeta que NO esté en OneDrive/Google Drive, p. ej. C:\hun_data"
