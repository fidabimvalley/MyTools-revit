@echo off
setlocal
title Uninstall MyTools for Revit
echo.
tasklist /FI "IMAGENAME eq Revit.exe" 2>nul | find /I "Revit.exe" >nul
if not errorlevel 1 (
  echo   Revit is open. Please close Revit, then run this again.
  echo.
  pause
  exit /b 1
)
set /p "OK=  Remove MyTools from this PC? (Y/N) "
if /I not "%OK%"=="Y" exit /b 0

powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "foreach ($v in '2025', '2026') { $f = Join-Path $env:APPDATA ('Autodesk\Revit\Addins\' + $v + '\MyTools.addin'); if (Test-Path $f) { Remove-Item $f -Force; Write-Host ('  Removed from Revit ' + $v) } };" ^
  "foreach ($d in (Join-Path $env:APPDATA 'MyTools'), (Join-Path $env:APPDATA 'MyToolsVault\MyTools')) { if (Test-Path $d) { Remove-Item $d -Recurse -Force } }"

echo.
echo   MyTools has been removed.
echo.
pause
