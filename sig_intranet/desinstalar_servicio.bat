@echo off
REM ============================================
REM DESINSTALAR SERVICIO SIG INTRANET
REM Ejecutar como ADMINISTRADOR
REM ============================================

net session >nul 2>&1
if %errorLevel% neq 0 (
    echo [ERROR] Ejecutar como ADMINISTRADOR
    pause
    exit /b 1
)

set SERVICIO=SIGIntranet
set NSSM_PATH=C:\nssm\nssm.exe

echo Deteniendo servicio...
net stop %SERVICIO% 2>nul

echo Eliminando servicio...
%NSSM_PATH% remove %SERVICIO% confirm

echo.
echo [OK] Servicio eliminado.
pause
