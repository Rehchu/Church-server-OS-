<#
.SYNOPSIS
  Arise Server — Windows mode installer (Windows 10/11, run as Administrator).

.DESCRIPTION
  Windows mode runs three of the five things Arise Server does:
    - the dashboard on http://localhost:4147
    - the nightly YouTube automator at 2:05 AM
    - the restic backups and the GitHub mirror

  It does NOT give you a directory. A Windows 10/11 PC cannot be an Active
  Directory domain controller, so the Macs cannot bind, there are no domain
  accounts and no server-side user profiles. Those need the Linux install
  (installer/install.sh on Ubuntu Server 24.04). This script says so again at
  the end so nobody is surprised later.

  Everything goes under C:\Arise:
    C:\Arise\app          this repo
    C:\Arise\venv         Python
    C:\Arise\config       arise.toml, backups.yaml, secrets\
    C:\Arise\data         homes\ shares\ automator\ apps\ backups\
    C:\Arise\logs

  Idempotent: run it again any time. -DryRun prints every step and changes
  nothing. Standard -WhatIf is honoured on the cmdlets that support it.

.PARAMETER DryRun
  Print what would happen; change nothing.

.PARAMETER RepoUrl
  Where to clone from. Default: https://github.com/Rehchu/Church-server-OS-.git

.PARAMETER Branch
  Branch to check out. Default: main

.EXAMPLE
  PS> Set-ExecutionPolicy -Scope Process Bypass; .\install.ps1
#>
[CmdletBinding(SupportsShouldProcess = $true)]
param(
  [switch]$DryRun,
  [string]$RepoUrl = 'https://github.com/Rehchu/Church-server-OS-.git',
  [string]$Branch = 'main'
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

# ---- fixed names (match docs/ARCHITECTURE.md) ------------------------------
$Root       = 'C:\Arise'
$AppDir     = Join-Path $Root 'app'
$VenvDir    = Join-Path $Root 'venv'
$ConfigDir  = Join-Path $Root 'config'
$SecretsDir = Join-Path $ConfigDir 'secrets'
$DataDir    = Join-Path $Root 'data'
$LogDir     = Join-Path $Root 'logs'
$WebPort    = 4147
$PythonExe  = Join-Path $VenvDir 'Scripts\python.exe'
$LogFile    = Join-Path $LogDir 'install.log'

function Say  { param([string]$m) Write-Host "`n==> $m" -ForegroundColor Red }
function Note { param([string]$m) Write-Host "    $m" }
function Warn { param([string]$m) Write-Host "    ! $m" -ForegroundColor Yellow }
function Log  { param([string]$m) if (-not $DryRun) { Add-Content -Path $LogFile -Value ("{0}  {1}" -f (Get-Date -Format 's'), $m) } }

# Run a command, or print it in -DryRun.
function Invoke-Step {
  param([string]$Label, [scriptblock]$Action)
  if ($DryRun) { Note "[dry-run] $Label"; Log "[dry-run] $Label"; return }
  Note $Label
  Log $Label
  & $Action
}

# ---- preflight --------------------------------------------------------------
Say 'Preflight'
$isAdmin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $isAdmin) { throw 'Run this from an Administrator PowerShell (right-click → Run as administrator).' }

if (-not $DryRun) {
  New-Item -ItemType Directory -Force -Path $LogDir | Out-Null
  Add-Content -Path $LogFile -Value "============ Arise Server Windows install started $(Get-Date -Format 's')"
}
Note ("Windows: " + (Get-CimInstance Win32_OperatingSystem).Caption)
Note ("Computer: " + $env:COMPUTERNAME)

$winget = Get-Command winget -ErrorAction SilentlyContinue
if (-not $winget) {
  Warn 'winget is not available. Install "App Installer" from the Microsoft Store, then run this again.'
  Warn 'Without winget this script cannot install Python, Git or restic for you.'
}

function Install-WithWinget {
  param([string]$Id, [string]$Check)
  if (Get-Command $Check -ErrorAction SilentlyContinue) { Note "$Check already installed"; return }
  if (-not $winget) { Warn "$Check missing and winget unavailable; install it by hand"; return }
  Invoke-Step "winget install $Id" {
    & winget install --id $Id --exact --silent --accept-package-agreements --accept-source-agreements | Out-Null
    # winget does not refresh this session's PATH; pull it from the registry.
    $env:Path = [Environment]::GetEnvironmentVariable('Path', 'Machine') + ';' + [Environment]::GetEnvironmentVariable('Path', 'User')
  }
}

# ---- 1. tools ---------------------------------------------------------------
Say '1/6  Python 3.12, Git, restic'
Install-WithWinget -Id 'Python.Python.3.12' -Check 'py'
Install-WithWinget -Id 'Git.Git'            -Check 'git'
Install-WithWinget -Id 'restic.restic'      -Check 'restic'

# Pick a Python 3.11+ explicitly. "python" on PATH is often the Store stub.
$BasePython = $null
foreach ($v in '3.13', '3.12', '3.11') {
  if (Get-Command py -ErrorAction SilentlyContinue) {
    & py "-$v" -c 'import sys' 2>$null
    if ($LASTEXITCODE -eq 0) { $BasePython = @('py', "-$v"); break }
  }
}
if (-not $BasePython) {
  if (Get-Command python -ErrorAction SilentlyContinue) { $BasePython = @('python') }
  else { if (-not $DryRun) { throw 'No Python 3.11+ found after install. Install it from python.org (tick "Add to PATH") and run again.' } else { Warn 'No Python found (dry run continues)' } }
}
if ($BasePython) { Note ("python launcher: " + ($BasePython -join ' ')) }

# ---- 2. folders -------------------------------------------------------------
Say "2/6  Folders under $Root"
foreach ($d in @($Root, $AppDir, $ConfigDir, $SecretsDir, $DataDir, $LogDir,
                 (Join-Path $DataDir 'homes'), (Join-Path $DataDir 'shares'),
                 (Join-Path $DataDir 'automator'), (Join-Path $DataDir 'apps'),
                 (Join-Path $DataDir 'backups'), (Join-Path $DataDir 'backups\github-mirror'))) {
  if (-not (Test-Path $d)) { Invoke-Step "mkdir $d" { New-Item -ItemType Directory -Force -Path $d | Out-Null } }
}
# secrets\ readable by Administrators and SYSTEM only.
Invoke-Step "lock down $SecretsDir" {
  & icacls $SecretsDir /inheritance:r /grant:r 'Administrators:(OI)(CI)F' 'SYSTEM:(OI)(CI)F' | Out-Null
}

# ---- 3. code ----------------------------------------------------------------
Say "3/6  Code → $AppDir"
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$repoHere = Resolve-Path (Join-Path $here '..') -ErrorAction SilentlyContinue
if ($repoHere -and (Test-Path (Join-Path $repoHere 'docs\ARCHITECTURE.md')) -and ((Resolve-Path $repoHere).Path -ne $AppDir)) {
  # Running from a checkout somewhere else: copy it in (robocopy mirrors, skips .git).
  Invoke-Step "robocopy $repoHere → $AppDir" {
    & robocopy $repoHere.Path $AppDir /MIR /XD .git venv __pycache__ /XF *.pyc /NFL /NDL /NJH /NJS /NP | Out-Null
    if ($LASTEXITCODE -ge 8) { throw "robocopy failed with $LASTEXITCODE" }
  }
} elseif (Test-Path (Join-Path $AppDir '.git')) {
  Invoke-Step "git pull in $AppDir" { & git -C $AppDir pull --ff-only }
} elseif (Get-Command git -ErrorAction SilentlyContinue) {
  Invoke-Step "git clone $RepoUrl ($Branch) → $AppDir" { & git clone --branch $Branch $RepoUrl $AppDir }
} else {
  Warn "No git and no checkout next to this script; copy the repo to $AppDir by hand."
}

# ---- 4. python venv ---------------------------------------------------------
Say "4/6  Python venv → $VenvDir"
if (-not (Test-Path $PythonExe)) {
  Invoke-Step "create venv" {
    if ($BasePython.Count -gt 1) { & $BasePython[0] $BasePython[1] -m venv $VenvDir }
    else { & $BasePython[0] -m venv $VenvDir }
  }
} else { Note 'venv exists' }
$req = Join-Path $AppDir 'server\requirements.txt'
Invoke-Step "pip install requirements + automator libs" {
  & $PythonExe -m pip install --quiet --upgrade pip
  if (Test-Path $req) { & $PythonExe -m pip install --quiet -r $req }
  else { & $PythonExe -m pip install --quiet fastapi 'uvicorn[standard]' psutil pyyaml bcrypt itsdangerous python-multipart }
  & $PythonExe -m pip install --quiet google-api-python-client google-auth-oauthlib pillow tzdata youtube-transcript-api
}

# ---- 5. config --------------------------------------------------------------
Say "5/6  Config → $ConfigDir"
$toml = Join-Path $ConfigDir 'arise.toml'
if (-not (Test-Path $toml)) {
  Invoke-Step "write arise.toml (profile = windows)" {
    $example = Get-Content (Join-Path $AppDir 'config\arise.toml.example') -Raw
    $w = $example `
      -replace 'profile = "server"', 'profile = "windows"' `
      -replace 'data_root = "/srv/arise"', 'data_root = "C:/Arise/data"' `
      -replace 'enabled = true\s*\r?\nrealm', "enabled = false`nrealm" `
      -replace 'homes_path = "/srv/arise/homes"', 'homes_path = "C:/Arise/data/homes"' `
      -replace 'path = "/srv/arise/automator/ARISE_YouTube_Updater"', 'path = "C:/Arise/data/automator/ARISE_YouTube_Updater"' `
      -replace 'python = "/opt/arise/venv/bin/python"', 'python = "C:/Arise/venv/Scripts/python.exe"' `
      -replace 'restic_repo = "/mnt/synology/arise-backups/restic"', 'restic_repo = "//SYNOLOGY/arise/arise-backups/restic"' `
      -replace 'password_file = "/etc/arise/secrets/restic-password"', 'password_file = "C:/Arise/config/secrets/restic-password"' `
      -replace 'jobs_file = "/etc/arise/backups.yaml"', 'jobs_file = "C:/Arise/config/backups.yaml"' `
      -replace 'mount = "/mnt/synology"', 'mount = "Z:"' `
      -replace 'dsm_credentials_file = "/etc/arise/secrets/dsm.json"', 'dsm_credentials_file = "C:/Arise/config/secrets/dsm.json"' `
      -replace 'docker = true', 'docker = false' `
      -replace 'root = "/srv/arise/apps"', 'root = "C:/Arise/data/apps"' `
      -replace 'mirror_path = "/srv/arise/backups/github-mirror"', 'mirror_path = "C:/Arise/data/backups/github-mirror"'
    Set-Content -Path $toml -Value $w -Encoding UTF8
  }
} else { Note 'arise.toml exists, left alone' }
$jobs = Join-Path $ConfigDir 'backups.yaml'
if (-not (Test-Path $jobs)) {
  Invoke-Step "write backups.yaml (Windows paths)" {
    $y = Get-Content (Join-Path $AppDir 'config\backups.yaml.example') -Raw
    $y = $y -replace '/srv/arise/', 'C:/Arise/data/' -replace '"/etc/arise", "/etc/samba", "/var/lib/samba/private"', '"C:/Arise/config"'
    Set-Content -Path $jobs -Value $y -Encoding UTF8
  }
} else { Note 'backups.yaml exists, left alone' }

# ---- 6. scheduled tasks + firewall ------------------------------------------
Say '6/6  Scheduled tasks and the firewall'
$serverDir   = Join-Path $AppDir 'server'
$arisectl    = Join-Path $AppDir 'cli\arisectl'
$automator   = Join-Path $DataDir 'automator\ARISE_YouTube_Updater'
$automatorPy = Join-Path $automator 'automator\arise_daily.py'

function Register-AriseTask {
  param([string]$Name, [string]$Exe, [string]$Args, [string]$WorkDir, $Trigger)
  $action    = New-ScheduledTaskAction -Execute $Exe -Argument $Args -WorkingDirectory $WorkDir
  $settings  = New-ScheduledTaskSettingsSet -StartWhenAvailable -ExecutionTimeLimit (New-TimeSpan -Hours 6) -MultipleInstances IgnoreNew -RestartCount 2 -RestartInterval (New-TimeSpan -Minutes 5)
  $principal = New-ScheduledTaskPrincipal -UserId 'SYSTEM' -LogonType ServiceAccount -RunLevel Highest
  Invoke-Step "register task '$Name'" {
    if ($PSCmdlet.ShouldProcess($Name, 'Register scheduled task')) {
      Register-ScheduledTask -TaskName $Name -Action $action -Trigger $Trigger -Settings $settings -Principal $principal -Force | Out-Null
    }
  }
}

# The dashboard: at startup, keep running. SYSTEM so it runs with nobody logged on.
$webTrigger = New-ScheduledTaskTrigger -AtStartup
$webAction  = "-m arise_server --config `"$toml`""
Register-AriseTask -Name 'Arise Web' -Exe $PythonExe -Args $webAction -WorkDir $serverDir -Trigger $webTrigger
if (-not $DryRun) {
  # The web task must not be killed after 6 hours.
  $t = Get-ScheduledTask -TaskName 'Arise Web' -ErrorAction SilentlyContinue
  if ($t) { $t.Settings.ExecutionTimeLimit = 'PT0S'; Set-ScheduledTask -InputObject $t | Out-Null }
}

Register-AriseTask -Name 'Arise YouTube Automator' -Exe $PythonExe -Args "`"$automatorPy`"" -WorkDir $automator `
  -Trigger (New-ScheduledTaskTrigger -Daily -At '02:05')
Register-AriseTask -Name 'Arise Backup' -Exe $PythonExe -Args "`"$arisectl`" backup run" -WorkDir $AppDir `
  -Trigger (New-ScheduledTaskTrigger -Daily -At '03:00')
Register-AriseTask -Name 'Arise GitHub Mirror' -Exe $PythonExe -Args "`"$arisectl`" mirror run" -WorkDir $AppDir `
  -Trigger (New-ScheduledTaskTrigger -Daily -At '04:00')

# Firewall: the dashboard on 4147 from the LAN.
if (-not (Get-NetFirewallRule -DisplayName 'Arise Server dashboard' -ErrorAction SilentlyContinue)) {
  Invoke-Step "open TCP $WebPort inbound" {
    New-NetFirewallRule -DisplayName 'Arise Server dashboard' -Direction Inbound -Protocol TCP -LocalPort $WebPort -Action Allow -Profile Private,Domain | Out-Null
  }
} else { Note 'firewall rule exists' }

# Start the dashboard now.
if (-not $DryRun) {
  Start-ScheduledTask -TaskName 'Arise Web' -ErrorAction SilentlyContinue
  Start-Sleep -Seconds 3
  try { Invoke-WebRequest -UseBasicParsing "http://127.0.0.1:$WebPort/" -TimeoutSec 5 | Out-Null; Note "dashboard answering on :$WebPort" }
  catch { Warn "dashboard not answering on :$WebPort yet — look at $LogDir and Task Scheduler → 'Arise Web' → History" }
}

# ---- summary ----------------------------------------------------------------
Say 'Done. What still needs you'
Write-Host @"

    Dashboard     http://localhost:$WebPort   (from another PC: http://$($env:COMPUTERNAME):$WebPort)
    Code          $AppDir
    Config        $toml
    Data          $DataDir
    Log           $LogFile

    Still needs a human — in this order:

    1. Dashboard password:     & "$PythonExe" "$arisectl" admin set-password
    2. The automator checkout: git clone https://github.com/Rehchu/arise-youtube-automation.git "$automator"
       then copy token.json and client_secret.json into "$automator\"
       (they are never in git — bring them from the old folder D:\Arise Church Youtube Stuff\ARISE_YouTube_Updater)
    3. restic password:        write one line into $SecretsDir\restic-password
       KEEP A COPY OFF THIS PC. Without it the backups cannot be read.
    4. Synology:               map the NAS share as Z: (File Explorer → Map network drive, reconnect at sign-in),
       and set [backups] restic_repo in arise.toml to the folder on it.
    5. Then:                   & "$PythonExe" "$arisectl" doctor

    ------------------------------------------------------------------
    WINDOWS MODE HAS NO DIRECTORY.
    A Windows 10/11 PC cannot be an Active Directory domain controller.
    No domain accounts, no Mac binding, no server-side user profiles
    on this install. Those need the Linux install (installer/install.sh
    on Ubuntu Server 24.04) — see INSTALL.md, Path A.
    ------------------------------------------------------------------
$(if ($DryRun) { '    (dry run: NOTHING WAS CHANGED)' })
"@
Log 'finished'
