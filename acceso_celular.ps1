# Acceso desde el celular: levanta la app y abre un tunel HTTPS de Cloudflare.
# Genera una URL publica nueva cada vez y muestra el QR para escanear.
$ErrorActionPreference = "Continue"

$app  = Split-Path -Parent $MyInvocation.MyCommand.Path
$py   = "C:\Users\Admin\AppData\Local\Programs\Python\Python312\python.exe"
$cf   = "C:\Users\Admin\Documents\Default Project\herramientas\cloudflared.exe"
$tmp  = Join-Path $env:TEMP "ordenes_tunel"
New-Item -ItemType Directory -Path $tmp -Force | Out-Null

Write-Host ""
Write-Host "=== Ordenes de Servicio - acceso desde el celular ===" -ForegroundColor Cyan

# 1) App local
$escucha = Get-NetTCPConnection -LocalPort 8001 -State Listen -ErrorAction SilentlyContinue
if (-not $escucha) {
    Write-Host "[1/3] Iniciando la app..." -ForegroundColor Yellow
    Start-Process -FilePath $py -ArgumentList "app.py" -WorkingDirectory $app -WindowStyle Hidden `
        -RedirectStandardOutput (Join-Path $app "server.log") -RedirectStandardError (Join-Path $app "server.err")
    Start-Sleep -Seconds 4
} else {
    Write-Host "[1/3] La app ya esta corriendo en el puerto 8001." -ForegroundColor Green
}

# 2) Tunel
Get-CimInstance Win32_Process -Filter "Name='cloudflared.exe'" |
    ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
Get-ChildItem $tmp | Remove-Item -Force -ErrorAction SilentlyContinue

Write-Host "[2/3] Abriendo el tunel publico (10-30 segundos)..." -ForegroundColor Yellow
Start-Process -FilePath $cf -ArgumentList @("tunnel", "--url", "http://127.0.0.1:8001", "--no-autoupdate",
    "--logfile", (Join-Path $tmp "cf.log")) -WindowStyle Hidden `
    -RedirectStandardOutput (Join-Path $tmp "cf.out") -RedirectStandardError (Join-Path $tmp "cf.err")

$url = $null
for ($i = 0; $i -lt 45; $i++) {
    Start-Sleep -Seconds 2
    $texto = (Get-Content (Join-Path $tmp "cf.err"), (Join-Path $tmp "cf.out"), (Join-Path $tmp "cf.log") -Raw -ErrorAction SilentlyContinue) -join "`n"
    $m = [regex]::Match($texto, 'https://[a-z0-9-]+\.trycloudflare\.com')
    if ($m.Success) { $url = $m.Value; break }
}

if (-not $url) {
    Write-Host "No se pudo crear el tunel. Revisa tu conexion a internet." -ForegroundColor Red
    Read-Host "Enter para salir"
    exit 1
}

$url | Set-Content (Join-Path $tmp "url.txt") -Encoding UTF8

# 3) QR
Write-Host "[3/3] Generando el codigo QR..." -ForegroundColor Yellow
$png = Join-Path $tmp "qr.png"
$script = @"
import qrcode
qr = qrcode.QRCode(box_size=12, border=4)
qr.add_data(r'$url')
qr.make(fit=True)
qr.make_image(fill_color='#0f172a', back_color='white').convert('RGB').save(r'$png', 'PNG')
"@
$script | Set-Content (Join-Path $tmp "qr.py") -Encoding UTF8
& $py (Join-Path $tmp "qr.py") | Out-Null
if (Test-Path $png) { Start-Process $png }

Write-Host ""
Write-Host "  URL para el celular:" -ForegroundColor Cyan
Write-Host "  $url" -ForegroundColor White
Write-Host ""
Write-Host "  Escanea el QR que se abrio, o escribe la URL en el navegador." -ForegroundColor Gray
Write-Host "  El celular y este PC deben tener internet." -ForegroundColor Gray
Write-Host "  Mientras esta ventana siga abierta, el enlace funciona." -ForegroundColor Gray
Write-Host ""
Write-Host "  Deja esta ventana abierta. Ctrl+C para cerrar." -ForegroundColor Yellow
while ($true) { Start-Sleep -Seconds 3600 }
