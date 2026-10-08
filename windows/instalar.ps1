# Instala (o pone al día) One TV en Windows con un solo comando. En PowerShell (Inicio → escribe «PowerShell»):
#
#   irm https://raw.githubusercontent.com/julai1433/one-tv/main/windows/instalar.ps1 | iex
#
# (O doble clic en «Instalar One TV.cmd», que corre lo mismo.)
#
# Baja el proyecto a la carpeta «one-tv» de tu usuario (lo tuyo que ya esté ahí, como config.json, se queda), deja
# un acceso «One TV» en el Escritorio, instala con winget lo que falte (Python y ffmpeg), deja el servidor corriendo
# y arrancando solo al iniciar sesión, y abre el navegador en la bienvenida (http://localhost:8765/bienvenida), que
# termina la configuración. Volver a correrlo lo pone al día. Pide permiso de administrador una sola vez, para que
# la TV y el teléfono puedan conectarse (la regla «One TV» del Firewall de Windows); lo demás, sin permisos.
$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'   # (la barra de progreso de PowerShell 5.1 hace muy lenta la descarga)
$zip = 'https://github.com/julai1433/one-tv/archive/refs/heads/main.zip'
$destino = Join-Path $HOME 'one-tv'
$tmp = Join-Path ([IO.Path]::GetTempPath()) ('one-tv-' + [guid]::NewGuid())
New-Item -ItemType Directory -Path $tmp | Out-Null
try {
    Write-Host 'Bajando One TV…'
    [Net.ServicePointManager]::SecurityProtocol = [Net.ServicePointManager]::SecurityProtocol -bor
        [Net.SecurityProtocolType]::Tls12
    Invoke-WebRequest -UseBasicParsing -Uri $zip -OutFile (Join-Path $tmp 'one-tv.zip')
    Expand-Archive -Path (Join-Path $tmp 'one-tv.zip') -DestinationPath (Join-Path $tmp 'x')
    $origen = Get-ChildItem (Join-Path $tmp 'x') -Directory | Select-Object -First 1
    # Copia encima, sin borrar lo que no viene en el proyecto (config.json). robocopy sale con 0 a 7 si salió bien.
    robocopy $origen.FullName $destino /E /NFL /NDL /NJH /NJS /NP | Out-Null
    if ($LASTEXITCODE -ge 8) { throw "no se pudo copiar a $destino (robocopy: $LASTEXITCODE)" }
} finally {
    Remove-Item -Recurse -Force $tmp -ErrorAction SilentlyContinue
}
Write-Host "✓ One TV quedó en $destino"

try {
    $acceso = (New-Object -ComObject WScript.Shell).CreateShortcut(
        (Join-Path ([Environment]::GetFolderPath('Desktop')) 'One TV.lnk'))
    $acceso.TargetPath = Join-Path $destino 'cine.cmd'
    $acceso.WorkingDirectory = $destino
    $acceso.Description = 'One TV: tus películas y series en la TV'
    $acceso.Save()
    Write-Host '✓ Acceso «One TV» en el Escritorio (doble clic para arrancar)'
} catch {
    Write-Host "· No pude crear el acceso en el Escritorio: abre $destino y haz doble clic en cine.cmd"
}

Write-Host ''
# Lo último: Python y ffmpeg (con winget, sin preguntar: ya dijiste que sí al instalar), el permiso del firewall, el
# arranque automático y el navegador en la bienvenida (mac\cine.py, «instalador»).
$env:ONE_TV_INSTALAR = '1'
& (Join-Path $destino 'cine.cmd') instalador
$codigo = $LASTEXITCODE
Remove-Item Env:ONE_TV_INSTALAR -ErrorAction SilentlyContinue   # (esta ventana sigue abierta: que no se quede)
if ($codigo -ne 0) {
    Write-Host ''
    Write-Host "✗ One TV quedó en $destino, pero no pudo arrancar (arriba dice por qué)."
    Write-Host '  Vuelve a correr el instalador; si sigue igual, avísanos en https://github.com/julai1433/one-tv/issues'
} else {
    Write-Host ''
    Write-Host 'Para ponerlo al día cuando quieras, vuelve a correr este mismo comando (tu configuración se queda).'
}
