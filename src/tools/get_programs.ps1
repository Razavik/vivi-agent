$utf8 = [System.Text.UTF8Encoding]::new($false)
[Console]::InputEncoding = $utf8
[Console]::OutputEncoding = $utf8
$OutputEncoding = $utf8

# Get installed programs from Windows Registry
$ErrorActionPreference = "Stop"
$programs = @()

try {
    $regPaths = @(
        'HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall',
        'HKLM:\SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall',
        'HKCU:\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall'
    )
    
    foreach ($path in $regPaths) {
        if (-not (Test-Path $path)) { continue }
        
        $keys = Get-ChildItem $path -ErrorAction Stop
        
        foreach ($key in $keys) {
            $props = Get-ItemProperty $key.PSPath -ErrorAction Stop
            $displayName = $props.DisplayName
            if ($displayName) {
                $prog = [PSCustomObject]@{
                    Name = $displayName
                    InstallLocation = $props.InstallLocation
                }
                $programs += $prog
            }
        }
    }
    
    if ($programs.Count -eq 0) {
        Write-Output "[]"
    } else {
        $programs | ConvertTo-Json -Depth 3
    }
} catch {
    Write-Error "Ошибка: $_"
    exit 1
}
