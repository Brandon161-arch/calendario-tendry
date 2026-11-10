@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo No se encontro la carpeta .venv.
  echo Ejecuta primero: python -m venv .venv ^&^& .venv\Scripts\pip install -r requirements.txt
  pause
  exit /b 1
)
".venv\Scripts\python.exe" run.py
endlocal
