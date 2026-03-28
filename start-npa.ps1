<#
.SYNOPSIS
    Startet den NPA (Next Policy Agent) Server.

.DESCRIPTION
    Startet den NPA-Server als Hintergrundprozess mit PID-Datei-Verwaltung,
    Health-Check nach dem Start und konfigurierbaren Optionen.

.PARAMETER Addr
    Adresse und Port (Standard: 0.0.0.0:8443)

.PARAMETER ConfigFile
    Pfad zur Konfigurationsdatei (YAML/JSON)

.PARAMETER NoTLS
    TLS deaktivieren

.PARAMETER Bundle
    Bundle-Pfad(e) zum Laden

.PARAMETER LogLevel
    Log-Level (debug, info, warning, error)

.PARAMETER TlsCert
    Pfad zum TLS-Zertifikat

.PARAMETER TlsKey
    Pfad zum TLS-Schlüssel

.PARAMETER PidFile
    Pfad zur PID-Datei (Standard: npa.pid)

.PARAMETER LogFile
    Pfad zur Log-Datei (Standard: npa.log)

.PARAMETER Foreground
    Server im Vordergrund starten (blockiert)

.EXAMPLE
    .\start-npa.ps1
    .\start-npa.ps1 -NoTLS
    .\start-npa.ps1 -Addr "0.0.0.0:9443" -ConfigFile config.yaml
    .\start-npa.ps1 -Foreground
#>

param(
    [string]$IniFile = "npa.ini",
    [string]$Addr = "",
    [string]$ConfigFile = "",
    [switch]$NoTLS,
    [string[]]$Bundle = @(),
    [string]$LogLevel = "",
    [string]$TlsCert = "",
    [string]$TlsKey = "",
    [string]$PidFile = "",
    [string]$LogFile = "",
    [switch]$Foreground
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

if (Test-Path $iniPath) {
    Write-Host "[NPA] Konfiguration geladen: $iniPath" -ForegroundColor Cyan
}

# INI-Werte als Defaults verwenden (CLI überschreibt)
function Get-IniVal([string]$section, [string]$key, [string]$default = "") {
    if ($ini.ContainsKey($section) -and $ini[$section].ContainsKey($key)) {
        $v = $ini[$section][$key]
        if ($v -ne "") { return $v }
    }
    return $default
}

# Server-Einstellungen aus INI (wenn nicht per CLI gesetzt)
if (-not $Addr) {
    $iniAddr = Get-IniVal "server" "addr"
    $iniPort = Get-IniVal "server" "port"
    if ($iniAddr -and $iniPort) { $Addr = "${iniAddr}:${iniPort}" }
}
if (-not $LogLevel)  { $LogLevel  = Get-IniVal "logging" "level" }
if (-not $TlsCert)   { $TlsCert   = Get-IniVal "tls" "cert_file" }
if (-not $TlsKey)    { $TlsKey    = Get-IniVal "tls" "key_file" }
if (-not $PidFile)   { $PidFile   = Get-IniVal "process" "pid_file" "npa.pid" }
if (-not $LogFile)   { $LogFile   = Get-IniVal "logging" "log_file" "npa.log" }
if (-not $PSBoundParameters.ContainsKey('NoTLS')) {
    $tlsEnabled = Get-IniVal "tls" "enabled" "true"
    if ($tlsEnabled -eq "false") { $NoTLS = [switch]::new($true) }
}
if (-not $PSBoundParameters.ContainsKey('Foreground')) {
    $fgVal = Get-IniVal "process" "foreground" "false"
    if ($fgVal -eq "true") { $Foreground = [switch]::new($true) }
}
if ($Bundle.Count -eq 0) {
    $iniBundles = Get-IniVal "bundles" "paths"
    if ($iniBundles) { $Bundle = $iniBundles -split ',' | ForEach-Object { $_.Trim() } | Where-Object { $_ } }
}

# ----- Hilfsfunktionen -----

function Write-Status([string]$msg) {
    Write-Host "[NPA] $msg" -ForegroundColor Cyan
}

function Write-Ok([string]$msg) {
    Write-Host "[NPA] $msg" -ForegroundColor Green
}

function Write-Err([string]$msg) {
    Write-Host "[NPA] $msg" -ForegroundColor Red
}

function Get-PythonExe {
    # Prüfe venv im Projektverzeichnis
    $venvPython = Join-Path $ScriptDir ".venv\Scripts\python.exe"
    if (Test-Path $venvPython) { return $venvPython }

    $venvPython = Join-Path $ScriptDir "venv\Scripts\python.exe"
    if (Test-Path $venvPython) { return $venvPython }

    # Fallback: System-Python
    $sysPython = Get-Command python -ErrorAction SilentlyContinue
    if ($sysPython) { return $sysPython.Source }

    $sysPython = Get-Command python3 -ErrorAction SilentlyContinue
    if ($sysPython) { return $sysPython.Source }

    return $null
}

function Test-NpaRunning {
    $pidPath = Join-Path $ScriptDir $PidFile
    if (-not (Test-Path $pidPath)) { return $false }
    $pid = [int](Get-Content $pidPath -Raw).Trim()
    $proc = Get-Process -Id $pid -ErrorAction SilentlyContinue
    return ($null -ne $proc)
}

# ----- Prüfungen -----

# Bereits laufend?
if (Test-NpaRunning) {
    $pidPath = Join-Path $ScriptDir $PidFile
    $pid = (Get-Content $pidPath -Raw).Trim()
    Write-Err "NPA läuft bereits (PID $pid). Bitte zuerst mit stop-npa.ps1 stoppen."
    exit 1
}

# Python finden
$python = Get-PythonExe
if (-not $python) {
    Write-Err "Python nicht gefunden. Bitte Python 3.12+ installieren."
    exit 1
}

Write-Status "Python: $python"

# ----- Argumente aufbauen -----

$npaArgs = @("-m", "npa", "run")

if ($Addr)       { $npaArgs += "--addr"; $npaArgs += $Addr }
if ($ConfigFile) { $npaArgs += "--config-file"; $npaArgs += $ConfigFile }
if ($NoTLS)      { $npaArgs += "--no-tls" }
if ($LogLevel)   { $npaArgs += "--log-level"; $npaArgs += $LogLevel }
if ($TlsCert)    { $npaArgs += "--tls-cert-file"; $npaArgs += $TlsCert }
if ($TlsKey)     { $npaArgs += "--tls-private-key-file"; $npaArgs += $TlsKey }
foreach ($b in $Bundle) {
    $npaArgs += "--bundle"; $npaArgs += $b
}

# ----- Port für Health-Check bestimmen -----

$scheme = "https"
$port = 8443

if ($Addr -match ':(\d+)$') {
    $port = [int]$Matches[1]
}
if ($NoTLS) {
    $scheme = "http"
    if ($port -eq 8443) { $port = 8181 }
}

# ----- Starten -----

if ($Foreground) {
    Write-Status "Starte NPA im Vordergrund..."
    Write-Status "Befehl: $python $($npaArgs -join ' ')"
    $pidPath = Join-Path $ScriptDir $PidFile

    # Cleanup PID-Datei bei Beendigung
    try {
        $proc = Start-Process -FilePath $python -ArgumentList $npaArgs -WorkingDirectory $ScriptDir -NoNewWindow -PassThru
        Set-Content -Path $pidPath -Value $proc.Id -NoNewline
        Write-Ok "NPA gestartet (PID $($proc.Id))"
        $proc.WaitForExit()
    } finally {
        if (Test-Path $pidPath) { Remove-Item $pidPath -Force }
    }
    exit $proc.ExitCode
}

# Hintergrund-Start
Write-Status "Starte NPA im Hintergrund..."
Write-Status "Befehl: $python $($npaArgs -join ' ')"

$logPath = Join-Path $ScriptDir $LogFile
$pidPath = Join-Path $ScriptDir $PidFile

$proc = Start-Process -FilePath $python `
    -ArgumentList $npaArgs `
    -WorkingDirectory $ScriptDir `
    -WindowStyle Hidden `
    -RedirectStandardOutput $logPath `
    -RedirectStandardError (Join-Path $ScriptDir "npa-error.log") `
    -PassThru

Set-Content -Path $pidPath -Value $proc.Id -NoNewline

Write-Ok "NPA gestartet (PID $($proc.Id))"
Write-Status "Log-Datei: $logPath"
Write-Status "PID-Datei: $pidPath"

# ----- Health-Check -----

Write-Status "Warte auf Server-Bereitschaft..."

# PS 5.1: SSL-Zertifikatsvalidierung fuer selbstsignierte Certs deaktivieren
if ($scheme -eq "https") {
    try {
        Add-Type @"
using System.Net;
using System.Net.Security;
using System.Security.Cryptography.X509Certificates;
public class TrustAllCerts {
    public static void Enable() {
        ServicePointManager.ServerCertificateValidationCallback =
            delegate { return true; };
    }
}
"@
        [TrustAllCerts]::Enable()
    } catch {
        # Typ bereits geladen — ignorieren
        [System.Net.ServicePointManager]::ServerCertificateValidationCallback = { $true }
    }
    [System.Net.ServicePointManager]::SecurityProtocol = [System.Net.SecurityProtocolType]::Tls12
}

$maxWait = [int](Get-IniVal "process" "health_check_timeout" "15")
$waited = 0
$ready = $false

while ($waited -lt $maxWait) {
    Start-Sleep -Seconds 1
    $waited++

    # Prozess noch am Leben?
    if ($proc.HasExited) {
        Write-Err "NPA-Prozess ist unerwartet beendet worden (Exit-Code: $($proc.ExitCode))"
        Write-Err "Siehe Log: $logPath"
        if (Test-Path $pidPath) { Remove-Item $pidPath -Force }
        exit 1
    }

    # Health-Endpoint pruefen
    try {
        if ($PSVersionTable.PSVersion.Major -ge 7 -and $scheme -eq "https") {
            $resp = Invoke-WebRequest -Uri "${scheme}://127.0.0.1:${port}/health" -TimeoutSec 2 -SkipCertificateCheck -ErrorAction Stop
        } else {
            $resp = Invoke-WebRequest -Uri "${scheme}://127.0.0.1:${port}/health" -TimeoutSec 2 -UseBasicParsing -ErrorAction Stop
        }
        if ($resp.StatusCode -eq 200) {
            $ready = $true
            break
        }
    } catch {
        # Noch nicht bereit
    }
}

if ($ready) {
    Write-Ok "NPA ist bereit! ${scheme}://127.0.0.1:${port}"
    Write-Ok "Dashboard: ${scheme}://127.0.0.1:${port}/ui/"
} else {
    Write-Err "Health-Check fehlgeschlagen nach ${maxWait}s - Server antwortet nicht."
    Write-Status "Pruefe Log-Datei: $logPath"
    $npaPid = $proc.Id
    Write-Status "Prozess laeuft noch (PID $npaPid) - ggf. manuell stoppen."
}
