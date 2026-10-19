@echo off
REM CyberSec AI Agent launcher (Windows)
cd /d "%~dp0"
if "%AGENT_MODEL%"=="" set AGENT_MODEL=dolphin-phi

where python >nul 2>nul
if errorlevel 1 (
  echo Python 3.8+ is required: https://www.python.org/downloads/
  pause & exit /b 1
)

where ollama >nul 2>nul
if errorlevel 1 (
  echo [!] Ollama not found. Install it from https://ollama.com  or use LM Studio.
  echo     The log analyzer still works without AI.
) else (
  curl -s -o nul http://127.0.0.1:11434/api/tags || (echo [*] Starting Ollama... & start "" /b ollama serve & timeout /t 3 >nul)
  for /f "skip=1" %%m in ('ollama list') do goto :run
  echo [*] No models found - downloading %AGENT_MODEL% (one-time^)...
  ollama pull %AGENT_MODEL%
)

:run
python agent.py %*
pause
