@echo off
REM Install the GLPI Agent on a Windows server from the offline bundle.
REM Usage (as Administrator):  install-agent-windows.cmd http://<glpi-server>/
REM Put GLPI-Agent-<version>-x64.msi (and server-ca.crt in HTTPS mode) in the same folder.
setlocal
if "%~1"=="" (
  echo usage: %~nx0 http://glpi-server/
  exit /b 1
)
set "MSI="
for %%F in ("%~dp0GLPI-Agent-*-x64.msi") do set "MSI=%%~fF"
if not defined MSI (
  echo GLPI-Agent-*-x64.msi not found next to this script.
  exit /b 1
)
set "CAOPT="
if exist "%~dp0server-ca.crt" (
  copy /y "%~dp0server-ca.crt" "%ProgramData%\dc-glpi-server-ca.crt" >nul
  set "CAOPT=CA_CERT_FILE=%ProgramData%\dc-glpi-server-ca.crt"
)
msiexec /i "%MSI%" /quiet SERVER="%~1" RUNNOW=1 EXECMODE=1 ADD_FIREWALL_EXCEPTION=1 %CAOPT% /l*v "%TEMP%\glpi-agent-install.log"
echo Exit code %ERRORLEVEL%. Log: %TEMP%\glpi-agent-install.log
endlocal
