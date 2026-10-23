@echo off
rem Juega Catan en el computador, sin proyector ni camara: el mouse hace de mano.
rem Clic derecho sobre la ventana = menu de gestos (senalar, puno, roca, paz...).
cd /d "%~dp0"
".venv\Scripts\python.exe" scripts\iniciar_prueba.py --simulate
echo.
pause
