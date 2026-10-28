#Requires -RunAsAdministrator
<#
.SYNOPSIS
  Join a church Windows PC to the Arise domain: the join, the church
  certificate, and the shares as drive letters. Nothing else (Bradly, round 4,
  answers 26 and 67: "a join script, drive letters, and the church
  certificate; nothing else").

.DESCRIPTION
  Run once, as an administrator, in Windows PowerShell 5.1 or PowerShell 7:

      Set-ExecutionPolicy -Scope Process Bypass
      .\join-arise.ps1 -ServerIp 192.168.1.20

  What it does, in order, and it stops at the first thing that fails:
    1. Checks the edition (Windows Home cannot join a domain).
    2. Name resolution WITHOUT touching the network: an NRPT rule sends only
       *.ad.arisecenla.com to the server (the Windows twin of the Macs'
       /etc/resolver file). The adapter's DNS, the router and the Mesh are not
       changed (docs/ANSWERS.md: the network stays as it is). Skipped with
       -NoDnsRule when the PC already resolves the domain (e.g. over Tailscale).
    3. Trusts the church certificate (the padlock on https://arise-server):
       downloads http://<server>:4147/ca.crt into LocalMachine\Root.
    4. Joins AD.ARISECENLA.COM into OU=PCs,OU=Computers (install.sh makes
       that OU). Asks for a domain admin's name and password.
    5. Installs a sign-in script for every user that maps the shares they may
       open as drive letters (H: home, S: church shares, the department shares
       by group); a share someone cannot open is simply not mapped.
    6. Offers the restart the join needs.

  Undo: Remove-Computer -UnjoinDomainCredential ARISE\administrator -Restart,
        Remove-DnsClientNrptRule -Name <the rule's name, from Get-DnsClientNrptRule>,
        delete C:\ProgramData\Arise and the StartUp file arise-drives.cmd.

.PARAMETER ServerIp
  The server's address on the church network (on the closet card; also
  `arisectl info` on the server). Required unless -NoDnsRule.
#>
[CmdletBinding()]
param(
    [string]$ServerIp = "",
    [string]$Server = "arise-server",
    [string]$Realm = "ad.arisecenla.com",
    [string]$NetBios = "ARISE",
    [string]$OU = "OU=PCs,OU=Computers,DC=ad,DC=arisecenla,DC=com",
    [string]$ComputerName = $env:COMPUTERNAME,
    [switch]$NoDnsRule,
    [switch]$NoRestart
)

$ErrorActionPreference = "Stop"
function Say([string]$m) { Write-Host "  $m" }
function Step([string]$m) { Write-Host ""; Write-Host "==> $m" -ForegroundColor Red }
function Fail([string]$m) { Write-Host ""; Write-Host "  FAILED: $m" -ForegroundColor Yellow; exit 1 }

$Fqdn = "$Server.$Realm"

# ---- 1. edition --------------------------------------------------------------
Step "1/6  Windows edition"
$os = Get-CimInstance Win32_OperatingSystem
Say "$($os.Caption) ($($os.Version))"
if ($os.Caption -match "Home") {
    Fail "Windows Home cannot join a domain. This PC needs Windows Pro (Settings > System > Activation > Upgrade), or use the shares without joining: \\$Server\shares in File Explorer."
}
if ((Get-CimInstance Win32_ComputerSystem).PartOfDomain) {
    $dom = (Get-CimInstance Win32_ComputerSystem).Domain
    if ($dom -ieq $Realm) { Say "already joined to $dom; only the certificate and the drives are checked" } else { Fail "this PC is joined to $dom. Leave that domain first (an administrator's job, not this script's)." }
}

# ---- 2. name resolution, scoped to the domain only ---------------------------
Step "2/6  Finding the server (only *.$Realm is asked of it)"
$resolves = $false
try { $null = Resolve-DnsName -Name "_ldap._tcp.dc._msdcs.$Realm" -Type SRV -DnsOnly -ErrorAction Stop; $resolves = $true } catch { $resolves = $false }
if ($resolves) {
    Say "the domain already resolves here; no rule needed"
} elseif ($NoDnsRule) {
    Fail "the domain does not resolve and -NoDnsRule was given. Connect Tailscale or give -ServerIp."
} else {
    if (-not $ServerIp) { Fail "give the server's church address: .\join-arise.ps1 -ServerIp 192.168.1.x (closet card, or 'arisectl info' on the server)" }
    if (-not (Test-Connection -ComputerName $ServerIp -Count 1 -Quiet)) { Fail "$ServerIp does not answer. Is this PC on the church network (or Tailscale)?" }
    $existing = Get-DnsClientNrptRule | Where-Object { $_.Namespace -contains ".$Realm" }
    if ($existing) {
        Say "an NRPT rule for .$Realm exists; leaving it"
    } else {
        Add-DnsClientNrptRule -Namespace ".$Realm" -NameServers $ServerIp -Comment "Arise: only the church domain goes to the server (join-arise.ps1)"
        Say "NRPT rule: .$Realm -> $ServerIp (the adapter's DNS is unchanged)"
    }
    Clear-DnsClientCache
    try { $null = Resolve-DnsName -Name "_ldap._tcp.dc._msdcs.$Realm" -Type SRV -DnsOnly -ErrorAction Stop }
    catch { Fail "the server at $ServerIp did not answer for $Realm. On the server: sudo arisectl doctor" }
    Say "the domain controller is found"
}

# ---- 3. the church certificate -----------------------------------------------
Step "3/6  The church certificate (the padlock)"
$tmp = Join-Path $env:TEMP "arise-ca.crt"
$caUrls = @("http://${Fqdn}:4147/ca.crt")
if ($ServerIp) { $caUrls += "http://${ServerIp}:4147/ca.crt" }
$got = $false
foreach ($u in $caUrls) {
    try { Invoke-WebRequest -Uri $u -OutFile $tmp -UseBasicParsing -TimeoutSec 10; $got = $true; break } catch { }
}
if (-not $got -or -not (Select-String -Path $tmp -Pattern "BEGIN CERTIFICATE" -Quiet)) {
    Say "could not fetch the certificate (Caddy not running on the server yet?); https will warn until it is trusted. Not fatal."
} else {
    $cert = New-Object System.Security.Cryptography.X509Certificates.X509Certificate2 $tmp
    $have = Get-ChildItem Cert:\LocalMachine\Root | Where-Object { $_.Thumbprint -eq $cert.Thumbprint }
    if ($have) { Say "already trusted: $($cert.Subject)" }
    else { Import-Certificate -FilePath $tmp -CertStoreLocation Cert:\LocalMachine\Root | Out-Null; Say "trusted: $($cert.Subject)" }
}

# ---- 4. the join -----------------------------------------------------------------
Step "4/6  Joining $Realm"
$needRestart = $false
if (-not (Get-CimInstance Win32_ComputerSystem).PartOfDomain) {
    Say "a domain admin's sign-in, e.g. $NetBios\administrator"
    $cred = Get-Credential -Message "Domain admin for $Realm (e.g. $NetBios\administrator)"
    try {
        Add-Computer -DomainName $Realm -OUPath $OU -Credential $cred -NewName $ComputerName -Force -ErrorAction Stop -WarningAction SilentlyContinue
    } catch {
        # a rename and a join in one call fail when the name is unchanged; try without -NewName
        try { Add-Computer -DomainName $Realm -OUPath $OU -Credential $cred -Force -ErrorAction Stop -WarningAction SilentlyContinue }
        catch { Fail "the join was refused: $($_.Exception.Message). Usual causes: the password, the OU (install.sh makes $OU), or a computer account with this name already in the domain (on the server: arisectl computer list)." }
    }
    Say "joined as $ComputerName in $OU"
    $needRestart = $true
}

# ---- 5. the drives, at every user's sign-in --------------------------------------
Step "5/6  Drive letters at sign-in"
$dir = "C:\ProgramData\Arise"
New-Item -ItemType Directory -Force -Path $dir | Out-Null
$map = @'
# Written by join-arise.ps1. Runs at every sign-in; maps the shares this person may open.
# A share they cannot open is skipped quietly. The letters: windows/README.md in the repo.
$server = "__SERVER__"
$drives = [ordered]@{
    "H" = $env:USERNAME          # the home folder ([homes] answers to the user's own name)
    "S" = "shares"               # the church folder everyone signed in shares
    "T" = "staff"
    "L" = "leadership"
    "M" = "media"
    "G" = "graphics"
    "W" = "worship"
    "K" = "kids"
    "J" = "childrens-department"
    "I" = "inedge"
    "R" = "recordings"
}
foreach ($letter in $drives.Keys) {
    $unc = "\\$server\$($drives[$letter])"
    if (Test-Path "${letter}:\") { continue }
    try { New-PSDrive -Name $letter -PSProvider FileSystem -Root $unc -Persist -Scope Global -ErrorAction Stop | Out-Null } catch { }
}
'@
$map = $map.Replace("__SERVER__", $Fqdn)
Set-Content -Path (Join-Path $dir "map-drives.ps1") -Value $map -Encoding UTF8
$startup = Join-Path $env:ProgramData "Microsoft\Windows\Start Menu\Programs\StartUp\arise-drives.cmd"
Set-Content -Path $startup -Encoding ASCII -Value "@powershell.exe -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$dir\map-drives.ps1`""
Say "every user's sign-in maps H: (home), S: (church) and the department shares they may open"

# ---- 6. restart ---------------------------------------------------------------------
Step "6/6  Done"
Say "the domain:      $Realm (sign in as first.last, e.g. ARISE\bradly.dyer)"
Say "the dashboard:   https://$Fqdn  (or http://${Fqdn}:4147)"
if ($needRestart -and -not $NoRestart) {
    $a = Read-Host "  The join needs a restart. Restart now? [y/N]"
    if ($a -match '^[yY]') { Restart-Computer -Force } else { Say "restart before signing in with a church account" }
} elseif ($needRestart) {
    Say "restart before signing in with a church account"
}
