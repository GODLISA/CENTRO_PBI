@echo off
REM ============================================
REM ELIMINAR TAREA PROGRAMADA SIG INTRANET
REM Ejecutar como ADMINISTRADOR
REM ============================================

net session >nul 2>&1
if %errorLevel% neq 0 (
    echo [ERROR] Ejecutar como ADMINISTRADOR
    pause
    exit /b 1
)

set TAREA=SIGIntranet

echo Deteniendo tarea...
schtasks /end /tn "%TAREA%" 2>nul

echo Eliminando tarea...
schtasks /delete /tn "%TAREA%" /f

echo.
echo [OK] Tarea eliminada.
pause
