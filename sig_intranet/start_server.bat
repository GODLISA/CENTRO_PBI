@echo off
REM ============================================
REM Script para iniciar SIG Intranet en producción
REM Ejecutar como: start_server.bat
REM O usar con NSSM para servicio de Windows
REM ============================================
REM
REM Se invoca "python.exe -m waitress" en vez de "waitress-serve.exe":
REM los lanzadores .exe del venv guardan la ruta de python que tenían al
REM crearse, por lo que se rompen si la carpeta del proyecto se mueve.
REM ============================================

set APP_DIR=C:\Tareas\SIGPOWERBI\CENTRO_PBI\sig_intranet
set PYTHON_EXE=%APP_DIR%\venv\Scripts\python.exe
set APP_ARGS=--listen=0.0.0.0:8000 --threads=4 sig_intranet.wsgi:application

cd /d %APP_DIR%
"%PYTHON_EXE%" -m waitress %APP_ARGS%
