@echo off
setlocal
title Install MyTools for Revit
echo.
echo   Installing MyTools for Revit 2025 and 2026...
echo.

tasklist /FI "IMAGENAME eq Revit.exe" 2>nul | find /I "Revit.exe" >nul
if not errorlevel 1 (
  echo   Revit is open. Please close Revit, then run this installer again.
  echo.
  pause
  exit /b 1
)

set "ZIPURL=https://github.com/fidabimvalley/MyTools-revit/releases/download/installer/MyTools-Revit.zip"

powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$ErrorActionPreference = 'Stop';" ^
  "[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12;" ^
  "$zip = Join-Path $env:TEMP 'MyTools-Revit.zip'; $tmp = Join-Path $env:TEMP 'MyTools-Revit';" ^
  "Invoke-WebRequest '%ZIPURL%' -OutFile $zip -UseBasicParsing;" ^
  "if (Test-Path $tmp) { Remove-Item $tmp -Recurse -Force };" ^
  "Expand-Archive $zip $tmp;" ^
  "& (Join-Path $tmp 'install.ps1');" ^
  "Remove-Item $zip, $tmp -Recurse -Force"

if errorlevel 1 (
  echo.
  echo   Installation failed. Check your internet connection and try again.
  echo.
  pause
  exit /b 1
)

echo.
echo   Done! Start Revit and open the MyTools tab, then click Sign In.
echo   The first time, Revit asks about loading MyTools: click "Always Load".
echo.
pause
