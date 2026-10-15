# Installs MyTools for Revit 2025 and 2026 for the current Windows user (no admin rights needed).
# Run by Install-MyTools.bat from the unzipped release.
$ErrorActionPreference = 'Stop'
$src  = $PSScriptRoot
$root = Join-Path $env:APPDATA 'MyTools'
$app  = Join-Path $root 'app'
$ext  = Join-Path $root 'MyTools.extension'

New-Item -ItemType Directory -Force $root, $ext | Out-Null
if (Test-Path $app) { Remove-Item $app -Recurse -Force }
Copy-Item (Join-Path $src 'app') $app -Recurse
Copy-Item (Join-Path $src 'vault.json') (Join-Path $ext 'vault.json') -Force

# The earlier pyRevit version of MyTools would add a second MyTools tab.
$old = Join-Path $env:APPDATA 'pyRevit\Extensions\MyTools.extension'
if (Test-Path $old) {
  Remove-Item $old -Recurse -Force
  Write-Host '  Removed the old pyRevit version of MyTools.'
}

$dll = [Security.SecurityElement]::Escape((Join-Path $app 'MyTools.Revit.dll'))
$manifest = @"
<?xml version="1.0" encoding="utf-8"?>
<RevitAddIns>
  <AddIn Type="Application">
    <Name>MyTools</Name>
    <Assembly>$dll</Assembly>
    <FullClassName>MyTools.Revit.App</FullClassName>
    <AddInId>55754002-C97D-51F1-8FB1-8C6DB390A095</AddInId>
    <VendorId>MyTools</VendorId>
    <VendorDescription>MyTools for Revit</VendorDescription>
  </AddIn>
</RevitAddIns>
"@
foreach ($v in '2025', '2026') {
  $dir = Join-Path $env:APPDATA "Autodesk\Revit\Addins\$v"
  New-Item -ItemType Directory -Force $dir | Out-Null
  [IO.File]::WriteAllText((Join-Path $dir 'MyTools.addin'), $manifest, (New-Object Text.UTF8Encoding $false))
  Write-Host "  Added to Revit $v"
}
