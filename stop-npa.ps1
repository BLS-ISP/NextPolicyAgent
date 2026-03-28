<#
.SYNOPSIS
    Stoppt den NPA (Next Policy Agent) Server.

.DESCRIPTION
    Fährt den laufenden NPA-Server zuverlässig herunter:
    1. Graceful Shutdown via SIGTERM / CloseMainWindow
    2. Wartezeit für sauberes Beenden
    3. Force-Kill als letzte Option

.PARAMETER PidFile
    Pfad zur PID-Datei (Standard: npa.pid)

.PARAMETER Force
    Sofortiges Beenden ohne Graceful Shutdown

.PARAMETER Timeout
    Sekunden Wartezeit für Graceful Shutdown (Standard: 10)

.EXAMPLE
    .\stop-npa.ps1
    .\stop-npa.ps1 -Force
    .\stop-npa.ps1 -Timeout 30
#>

param(
    [string]$IniFile = "npa.ini",
    [string]$PidFile = "",
    [switch]$Force,
    [int]$Timeout = 0
)

$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Definition

# ----- INI-Datei laden -----

function Read-IniFile([string]$Path) {
    $ini = @{}
    $section = ""
    if (-not (Test-Path $Path)) { return $ini }
    foreach ($line in Get-Content $Path) {
        $line = $line.Trim()
        if ($line -match '^\s*[;#]' -or $line -eq '') { continue }
        if ($line -match '^\[(.+)\]$') {
            $section = $Matches[1].Trim()
            if (-not $ini.ContainsKey($section)) { $ini[$section] = @{} }
        } elseif ($line -match '^([^=]+)=(.*)$') {
            $key = $Matches[1].Trim()
            $val = $Matches[2].Trim()
            if ($section) { $ini[$section][$key] = $val }
        }
    }
    return $ini
}

$iniPath = Join-Path $ScriptDir $IniFile
$ini = Read-IniFile $iniPath

function Get-IniVal([string]$section, [string]$key, [string]$default = "") {
    if ($ini.ContainsKey($section) -and $ini[$section].ContainsKey($key)) {
        $v = $ini[$section][$key]
        if ($v -ne "") { return $v }
    }
    return $default
}

# INI-Defaults anwenden (CLI überschreibt)
if (-not $PidFile)  { $PidFile  = Get-IniVal "process" "pid_file" "npa.pid" }
if ($Timeout -eq 0) { $Timeout  = [int](Get-IniVal "process" "shutdown_timeout" "10") }

if (Test-Path $iniPath) {
    Write-Host "[NPA] Konfiguration geladen: $iniPath" -ForegroundColor Cyan
}

function Write-Status([string]$msg) {
    Write-Host "[NPA] $msg" -ForegroundColor Cyan
}

function Write-Ok([string]$msg) {
    Write-Host "[NPA] $msg" -ForegroundColor Green
}

function Write-Err([string]$msg) {
    Write-Host "[NPA] $msg" -ForegroundColor Red
}

# ----- PID lesen -----

$pidPath = Join-Path $ScriptDir $PidFile

if (-not (Test-Path $pidPath)) {
    Write-Err "PID-Datei nicht gefunden ($pidPath). NPA scheint nicht zu laufen."
    exit 1
}

$pidRaw = (Get-Content $pidPath -Raw).Trim()
if (-not ($pidRaw -match '^\d+$')) {
    Write-Err "Ungültige PID in $pidPath : '$pidRaw'"
    Remove-Item $pidPath -Force
    exit 1
}

$npaId = [int]$pidRaw

# ----- Prozess prüfen -----

$proc = Get-Process -Id $npaId -ErrorAction SilentlyContinue
if (-not $proc) {
    Write-Status "Prozess $npaId existiert nicht mehr. Räume PID-Datei auf."
    Remove-Item $pidPath -Force
    Write-Ok "Aufgeräumt."
    exit 0
}

Write-Status "NPA-Prozess gefunden (PID $npaId)"

# ----- Force Kill -----

if ($Force) {
    Write-Status "Force-Stop angefordert..."
    Stop-Process -Id $npaId -Force -ErrorAction SilentlyContinue
    Start-Sleep -Milliseconds 500
    Remove-Item $pidPath -Force -ErrorAction SilentlyContinue
    Write-Ok "NPA wurde beendet (Force-Kill)."
    exit 0
}

# ----- Graceful Shutdown -----

Write-Status "Sende Shutdown-Signal an NPA (PID $npaId)..."

# Kindprozesse finden (uvicorn worker)
$children = Get-CimInstance Win32_Process | Where-Object { $_.ParentProcessId -eq $npaId }

# Hauptprozess beenden
try {
    # Versuche Ctrl+C / taskkill mit /T für Tree-Kill
    $null = & taskkill /PID $npaId /T 2>&1
} catch {
    Stop-Process -Id $npaId -ErrorAction SilentlyContinue
}

# Warten auf Beendigung
Write-Status "Warte auf Beendigung (max. ${Timeout}s)..."
$waited = 0
$stopped = $false

while ($waited -lt $Timeout) {
    Start-Sleep -Seconds 1
    $waited++

    $check = Get-Process -Id $npaId -ErrorAction SilentlyContinue
    if (-not $check) {
        $stopped = $true
        break
    }
    Write-Host "." -NoNewline
}
Write-Host ""

if (-not $stopped) {
    Write-Status "Graceful Shutdown fehlgeschlagen. Erzwinge Beendigung..."
    Stop-Process -Id $npaId -Force -ErrorAction SilentlyContinue

    # Kindprozesse ebenfalls beenden
    foreach ($child in $children) {
        Stop-Process -Id $child.ProcessId -Force -ErrorAction SilentlyContinue
    }
    Start-Sleep -Milliseconds 500
}

# ----- Aufräumen -----

if (Test-Path $pidPath) {
    Remove-Item $pidPath -Force
}

# Prüfe ob wirklich gestoppt
$final = Get-Process -Id $npaId -ErrorAction SilentlyContinue
if ($final) {
    Write-Err "WARNUNG: Prozess $npaId konnte nicht beendet werden!"
    exit 1
} else {
    Write-Ok "NPA wurde erfolgreich gestoppt."
}
