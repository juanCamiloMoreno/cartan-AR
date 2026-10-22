@echo off
rem Arranca Catan en el proyector. Se puede cambiar la camara y la pantalla:
rem   iniciar_catan.bat 1 1      (camara USB = 1, proyector = pantalla 1)
cd /d "%~dp0"
set CAM=%1
set SCR=%2
if "%CAM%"=="" set CAM=1
if "%SCR%"=="" set SCR=1
".venv\Scripts\python.exe" scripts\iniciar_prueba.py --camera %CAM% --screen %SCR%
echo.
pause
