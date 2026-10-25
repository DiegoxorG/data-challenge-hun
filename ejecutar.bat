@echo off
rem Doble clic para abrir el menú de reportes (main.py) con el Python del .venv del repo.
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo No encontre .venv en esta carpeta. Primero crea el entorno: ver README, "Puesta en marcha".
  pause
  exit /b 1
)
".venv\Scripts\python.exe" main.py
