@echo off
setlocal
title Install MyTools for Revit
echo.
echo   Installing MyTools for Revit...
echo.

set "DEST=%APPDATA%\pyRevit\Extensions\MyTools.extension"
set "ZIPURL=https://github.com/fidabimvalley/mytools-revit/archive/refs/heads/main.zip"

if not exist "%APPDATA%\pyRevit" if not exist "%PROGRAMDATA%\pyRevit" (
  echo   pyRevit doesn't seem to be installed on this PC.
  echo   Install it first from https://github.com/pyrevitlabs/pyRevit/releases
  echo   then run this installer again.
  echo.
  pause
  exit /b 1
)

powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$ErrorActionPreference = 'Stop';" ^
  "[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12;" ^
  "$zip = Join-Path $env:TEMP 'mytools-revit.zip'; $tmp = Join-Path $env:TEMP 'mytools-revit-unzip';" ^
  "Invoke-WebRequest '%ZIPURL%' -OutFile $zip -UseBasicParsing;" ^
  "if (Test-Path $tmp) { Remove-Item $tmp -Recurse -Force };" ^
  "Expand-Archive $zip $tmp;" ^
  "New-Item -ItemType Directory -Force '%DEST%' | Out-Null;" ^
  "Copy-Item (Join-Path $tmp 'mytools-revit-main\*') '%DEST%' -Recurse -Force;" ^
  "Remove-Item $zip, $tmp -Recurse -Force"

if errorlevel 1 (
  echo.
  echo   Installation failed. Check your internet connection and try again.
  echo.
  pause
  exit /b 1
)

echo.
echo   Done! MyTools is installed in:
echo   %DEST%
echo.
echo   Start Revit (or click pyRevit - Reload if it's open), then click MyTools - Sign In.
echo.
pause
