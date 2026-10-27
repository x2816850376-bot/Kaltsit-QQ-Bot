$ErrorActionPreference = 'SilentlyContinue'
$ts = 'C:\Program Files\Tailscale\tailscale.exe'
$ipn = 'C:\Program Files\Tailscale\tailscale-ipn.exe'
if (-not (Test-Path $ts)) { exit 1 }

# The Windows service can be running while the desktop client is still in
# NoState after a reboot. Starting IPN restores the saved login state.
Start-Process -FilePath $ipn -WindowStyle Hidden

for ($i = 0; $i -lt 45; $i++) {
    $ip = & $ts ip -4 2>$null
    if ($ip -match '^100\.\d+\.\d+\.\d+$') {
        & $ts serve --bg --yes 18885 | Out-Null
        exit 0
    }
    Start-Sleep -Seconds 2
}
exit 2
