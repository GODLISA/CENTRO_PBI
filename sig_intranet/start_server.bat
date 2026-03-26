@echo off
REM ============================================
REM Script para iniciar SIG Intranet en producción
REM Ejecutar como: start_server.bat
REM O usar con NSSM para servicio de Windows
REM ============================================

cd /d C:\Tareas\CENTRO_PBI\sig_intranet
C:\Tareas\CENTRO_PBI\sig_intranet\venv\Scripts\waitress-serve.exe --listen=0.0.0.0:8000 --threads=4 sig_intranet.wsgi:application
