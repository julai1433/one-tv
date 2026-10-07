# One TV en Windows: hace lo mismo que el archivo «cine» en macOS y Linux. Lo abre cine.cmd (doble clic) con lo que
# le escribas después: cine | cine configurar | cine autoarranque | cine quitar-autoarranque | cine estado | ...
# Antes revisa que estén Python (3.9 o más nuevo) y ffmpeg; si falta alguno, dice el comando exacto para instalarlo
# y ofrece instalarlo con winget (con solo contestar «s»).
# (Este archivo va en UTF-8 con BOM: así Windows PowerShell 5.1 lee bien los acentos.)
param([Parameter(ValueFromRemainingArguments = $true)] [string[]] $Resto)

$ErrorActionPreference = 'Stop'
$Proyecto = Split-Path -Parent $PSScriptRoot
$Local = if ($env:LOCALAPPDATA) { $env:LOCALAPPDATA } else { Join-Path $HOME 'AppData\Local' }

function Actualizar-Path {
    # Lo que se instaló después de abrir esta ventana (por ejemplo, recién con winget) todavía no está en su PATH:
    # se agrega lo que diga el registro, sin quitar nada.
    $partes = @($env:Path -split ';' | Where-Object { $_ })
    foreach ($alcance in 'Machine', 'User') {
        $valor = [Environment]::GetEnvironmentVariable('Path', $alcance)
        if (-not $valor) { continue }
        foreach ($p in ($valor -split ';')) {
            if ($p -and ($partes -notcontains $p)) { $partes += $p }
        }
    }
    $enlaces = Join-Path $Local 'Microsoft\WinGet\Links'
    if ((Test-Path $enlaces) -and ($partes -notcontains $enlaces)) { $partes += $enlaces }
    $env:Path = $partes -join ';'
}

function Probar-Python([string] $exe, [string[]] $antes) {
    # La ruta del python.exe de verdad si sirve (3.9 o más nuevo), o $null. (El «python» que Windows trae sin
    # Python instalado solo abre la Microsoft Store: con -c no hace nada y sale con error.)
    try {
        $salida = & $exe @antes -c 'import sys; print(sys.executable); sys.exit(0 if sys.version_info >= (3, 9) else 3)' 2>$null
        if ($LASTEXITCODE -eq 0 -and $salida) { return ([string]($salida | Select-Object -Last 1)).Trim() }
    } catch { }
    return $null
}

function Buscar-Python {
    # El Python de python.org primero; el de la Microsoft Store solo si no hay otro (guarda sus cosas en otra carpeta
    # que ffmpeg no ve).
    $candidatos = New-Object System.Collections.ArrayList
    if (Get-Command py -ErrorAction SilentlyContinue) { [void]$candidatos.Add(@('py', '-3')) }
    if (Get-Command python -ErrorAction SilentlyContinue) { [void]$candidatos.Add(@('python')) }
    foreach ($c in @((Join-Path $Local 'Programs\Python'), "$env:ProgramFiles")) {
        if (-not $c -or -not (Test-Path $c)) { continue }
        $versiones = Get-ChildItem $c -Directory -Filter 'Python3*' -ErrorAction SilentlyContinue |
            Sort-Object { [int]($_.Name -replace '\D', '') } -Descending
        foreach ($d in $versiones) {
            $exe = Join-Path $d.FullName 'python.exe'
            if (Test-Path $exe) { [void]$candidatos.Add(@($exe)) }
        }
    }
    $tienda = $null
    foreach ($c in $candidatos) {
        $ruta = Probar-Python $c[0] @($c | Select-Object -Skip 1)
        if (-not $ruta) { continue }
        if ($ruta -like '*\WindowsApps\*') {
            if (-not $tienda) { $tienda = $ruta }
            continue
        }
        return $ruta
    }
    return $tienda
}

function Preguntar([string] $pregunta) {
    if ($env:ONE_TV_SIN_PREGUNTAS) { return $false }   # (las pruebas automáticas: nunca instala nada)
    try { $r = Read-Host $pregunta } catch { return $false }
    return ($r -match '^\s*(s|si|sí|y|yes)\s*$')
}

function Instalar-Con-Winget([string] $id, [string] $nombre, [string[]] $extra) {
    # Muestra el comando exacto y, si la persona dice que sí, lo corre. Devuelve $true si quedó instalado.
    $comando = "winget install -e --id $id"
    if (-not (Get-Command winget -ErrorAction SilentlyContinue)) {
        Write-Host "  Para instalarlo hace falta «winget», que viene en el «Instalador de aplicación» de la Microsoft Store:"
        Write-Host '    https://apps.microsoft.com/detail/9NBLGGH4NNS1'
        Write-Host "  Después, en una ventana de comandos:  $comando   y vuelve a abrir cine.cmd."
        return $false
    }
    Write-Host '  Se instala con este comando:'
    Write-Host ''
    Write-Host "    $comando"
    Write-Host ''
    if (-not (Preguntar "  ¿Lo instalo ahora? Escribe s y pulsa Enter (solo Enter: no)")) {
        Write-Host '  Cuando lo instales, vuelve a abrir cine.cmd.'
        return $false
    }
    # (| Out-Host: que se vea lo que dice winget mientras instala)
    & winget install -e --id $id --accept-source-agreements --accept-package-agreements @extra | Out-Host
    if ($LASTEXITCODE -ne 0 -and $extra) {   # sin instalador «solo para tu usuario»: el normal
        & winget install -e --id $id --accept-source-agreements --accept-package-agreements | Out-Host
    }
    Actualizar-Path
    return $true
}

function Buscar-Ffmpeg {
    if ((Get-Command ffmpeg -ErrorAction SilentlyContinue) -and (Get-Command ffprobe -ErrorAction SilentlyContinue)) {
        return $true
    }
    # Recién instalado con winget, a veces todavía no está en el PATH: se busca en su carpeta.
    $paquetes = Join-Path $Local 'Microsoft\WinGet\Packages'
    if (Test-Path $paquetes) {
        $exe = Get-ChildItem $paquetes -Recurse -Filter 'ffprobe.exe' -ErrorAction SilentlyContinue | Select-Object -First 1
        if ($exe) {
            $env:Path += ";$($exe.DirectoryName)"
            return [bool](Get-Command ffmpeg -ErrorAction SilentlyContinue)
        }
    }
    return $false
}

Actualizar-Path

$python = Buscar-Python
if (-not $python -or $python -like '*\WindowsApps\*') {
    if (-not $python) {
        Write-Host '✗ Falta Python (3.9 o más nuevo), que One TV necesita.'
    } else {
        Write-Host '⚠ Tu Python es el de la Microsoft Store. One TV funciona mejor con el de python.org.'
    }
    if (Instalar-Con-Winget 'Python.Python.3.12' 'Python' @('--scope', 'user')) {
        $nuevo = Buscar-Python
        if ($nuevo) { $python = $nuevo }
    }
    if (-not $python) { exit 1 }
}

if (-not (Buscar-Ffmpeg)) {
    Write-Host '✗ Falta ffmpeg, que One TV necesita para preparar los videos para la TV.'
    $null = Instalar-Con-Winget 'Gyan.FFmpeg' 'ffmpeg' @()
    if (-not (Buscar-Ffmpeg)) { exit 1 }
}

# Textos en UTF-8, como en macOS y Linux (acentos de config.json, nombres de películas, lo que dicen ffmpeg y yt-dlp).
$env:PYTHONUTF8 = '1'
$cine = Join-Path $Proyecto 'mac\cine.py'
if ($Resto) { & $python -X utf8 $cine @Resto } else { & $python -X utf8 $cine }
exit $LASTEXITCODE
