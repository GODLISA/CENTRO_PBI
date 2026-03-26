@echo off
REM ============================================
REM INSTALAR SIG INTRANET COMO SERVICIO DE WINDOWS
REM Ejecutar como ADMINISTRADOR
REM ============================================
REM
REM OPCIÓN A: Usando NSSM (recomendado)
REM   1. Descargar nssm de https://nssm.cc/download
REM   2. Extraer nssm.exe en C:\nssm\ (o cualquier carpeta)
REM   3. Ejecutar este script como Administrador
REM
REM OPCIÓN B: Usando sc.exe nativo de Windows (ver abajo)
REM ============================================

echo.
echo ==========================================
echo   SIG Intranet - Instalador de Servicio
echo ==========================================
echo.

REM --- Verificar permisos de administrador ---
net session >nul 2>&1
if %errorLevel% neq 0 (
    echo [ERROR] Ejecutar este script como ADMINISTRADOR
    echo Clic derecho sobre el archivo ^> Ejecutar como administrador
    pause
    exit /b 1
)

REM --- Configuración ---
set SERVICIO=SIGIntranet
set NSSM_PATH=C:\nssm\nssm.exe
set WAITRESS_EXE=C:\Tareas\CENTRO_PBI\sig_intranet\venv\Scripts\waitress-serve.exe
set APP_DIR=C:\Tareas\CENTRO_PBI\sig_intranet
set APP_ARGS=--listen=0.0.0.0:8000 --threads=4 sig_intranet.wsgi:application

REM --- Verificar que NSSM existe ---
if not exist "%NSSM_PATH%" (
    echo [ERROR] No se encontro nssm.exe en %NSSM_PATH%
    echo.
    echo Descargalo de: https://nssm.cc/download
    echo Extrae nssm.exe en C:\nssm\
    echo.
    pause
    exit /b 1
)

REM --- Verificar que waitress existe ---
if not exist "%WAITRESS_EXE%" (
    echo [ERROR] No se encontro waitress-serve.exe
    echo Ejecuta: venv\Scripts\pip install waitress
    pause
    exit /b 1
)

echo Instalando servicio "%SERVICIO%"...
echo.

REM --- Instalar servicio con NSSM ---
%NSSM_PATH% install %SERVICIO% "%WAITRESS_EXE%"
%NSSM_PATH% set %SERVICIO% AppParameters "%APP_ARGS%"
%NSSM_PATH% set %SERVICIO% AppDirectory "%APP_DIR%"
%NSSM_PATH% set %SERVICIO% DisplayName "SIG Intranet - Panel Power BI"
%NSSM_PATH% set %SERVICIO% Description "Servidor web para panel de Power BI en intranet"
%NSSM_PATH% set %SERVICIO% Start SERVICE_AUTO_START
%NSSM_PATH% set %SERVICIO% AppStdout "%APP_DIR%\logs\service.log"
%NSSM_PATH% set %SERVICIO% AppStderr "%APP_DIR%\logs\error.log"
%NSSM_PATH% set %SERVICIO% AppRotateFiles 1
%NSSM_PATH% set %SERVICIO% AppRotateBytes 5242880

REM --- Crear carpeta de logs ---
if not exist "%APP_DIR%\logs" mkdir "%APP_DIR%\logs"

echo.
echo [OK] Servicio instalado correctamente.
echo.
echo Comandos utiles:
echo   Iniciar:    net start %SERVICIO%
echo   Detener:    net stop %SERVICIO%
echo   Eliminar:   %NSSM_PATH% remove %SERVICIO% confirm
echo   Estado:     sc query %SERVICIO%
echo   Logs:       %APP_DIR%\logs\
echo.

REM --- Iniciar el servicio ---
echo Iniciando servicio...
net start %SERVICIO%

echo.
echo ==========================================
echo   Servidor accesible en:
echo   http://172.16.0.13:8000
echo ==========================================
echo.
pause
