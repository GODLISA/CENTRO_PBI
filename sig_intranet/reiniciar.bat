@echo off
REM ============================================
REM REINICIAR SIG INTRANET (tarea programada)
REM Ejecutar como ADMINISTRADOR
REM ============================================
REM schtasks /end no siempre mata el proceso: este script lo termina por PID
REM y recien ahi vuelve a arrancar la tarea.
REM ============================================

net session >nul 2>&1
if %errorLevel% neq 0 (
    echo [ERROR] Ejecutar como ADMINISTRADOR
    pause
    exit /b 1
)

set TAREA=SIGIntranet
set PUERTO=8000

echo Deteniendo tarea "%TAREA%"...
schtasks /end /tn "%TAREA%" >nul 2>&1

echo Cerrando procesos que escuchan en el puerto %PUERTO%...
for /f "tokens=5" %%p in ('netstat -ano ^| findstr ":%PUERTO%" ^| findstr "LISTENING"') do (
    echo   taskkill PID %%p
    taskkill /PID %%p /F >nul 2>&1
)

echo Iniciando tarea...
schtasks /run /tn "%TAREA%" >nul

echo.
echo Estado del puerto %PUERTO%:
netstat -ano | findstr ":%PUERTO%" | findstr "LISTENING"
echo.
echo Si no aparece ninguna linea, revisa el arranque a mano con:
echo   venv\Scripts\python.exe -m waitress --listen=0.0.0.0:%PUERTO% --threads=4 sig_intranet.wsgi:application
echo.
pause
