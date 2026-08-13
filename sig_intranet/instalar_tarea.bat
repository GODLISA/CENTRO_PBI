@echo off
REM ============================================
REM REGISTRAR SIG INTRANET EN PROGRAMADOR DE TAREAS
REM Ejecutar como ADMINISTRADOR
REM No requiere instalar software adicional
REM ============================================

echo.
echo ==========================================
echo   SIG Intranet - Programador de Tareas
echo ==========================================
echo.

REM --- Verificar permisos de administrador ---
net session >nul 2>&1
if %errorLevel% neq 0 (
    echo [ERROR] Ejecutar este script como ADMINISTRADOR
    pause
    exit /b 1
)

REM --- Configuracion: ajustar APP_DIR si el proyecto cambia de carpeta ---
REM Se usa "python.exe -m waitress" en vez de "waitress-serve.exe" porque los
REM lanzadores .exe del venv se rompen si la carpeta del proyecto se mueve.
set TAREA=SIGIntranet
set APP_DIR=C:\Tareas\SIGPOWERBI\CENTRO_PBI\sig_intranet
set WAITRESS=%APP_DIR%\venv\Scripts\python.exe
set ARGS=-m waitress --listen=0.0.0.0:8000 --threads=4 sig_intranet.wsgi:application

REM --- Eliminar tarea si ya existe ---
schtasks /delete /tn "%TAREA%" /f 2>nul

REM --- Crear tarea programada ---
schtasks /create ^
  /tn "%TAREA%" ^
  /tr "\"%WAITRESS%\" %ARGS%" ^
  /sc onstart ^
  /ru SYSTEM ^
  /rl HIGHEST ^
  /f

REM --- Configurar directorio de trabajo via XML ---
echo Configurando directorio de trabajo...

echo ^<?xml version="1.0" encoding="UTF-16"?^> > "%TEMP%\sig_task.xml"
echo ^<Task version="1.2" xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task"^> >> "%TEMP%\sig_task.xml"
echo   ^<RegistrationInfo^> >> "%TEMP%\sig_task.xml"
echo     ^<Description^>Servidor web SIG Intranet - Panel Power BI^</Description^> >> "%TEMP%\sig_task.xml"
echo   ^</RegistrationInfo^> >> "%TEMP%\sig_task.xml"
echo   ^<Triggers^> >> "%TEMP%\sig_task.xml"
echo     ^<BootTrigger^> >> "%TEMP%\sig_task.xml"
echo       ^<Enabled^>true^</Enabled^> >> "%TEMP%\sig_task.xml"
echo       ^<Delay^>PT30S^</Delay^> >> "%TEMP%\sig_task.xml"
echo     ^</BootTrigger^> >> "%TEMP%\sig_task.xml"
echo   ^</Triggers^> >> "%TEMP%\sig_task.xml"
echo   ^<Principals^> >> "%TEMP%\sig_task.xml"
echo     ^<Principal id="Author"^> >> "%TEMP%\sig_task.xml"
echo       ^<UserId^>S-1-5-18^</UserId^> >> "%TEMP%\sig_task.xml"
echo       ^<RunLevel^>HighestAvailable^</RunLevel^> >> "%TEMP%\sig_task.xml"
echo     ^</Principal^> >> "%TEMP%\sig_task.xml"
echo   ^</Principals^> >> "%TEMP%\sig_task.xml"
echo   ^<Settings^> >> "%TEMP%\sig_task.xml"
echo     ^<MultipleInstancesPolicy^>IgnoreNew^</MultipleInstancesPolicy^> >> "%TEMP%\sig_task.xml"
echo     ^<DisallowStartIfOnBatteries^>false^</DisallowStartIfOnBatteries^> >> "%TEMP%\sig_task.xml"
echo     ^<StopIfGoingOnBatteries^>false^</StopIfGoingOnBatteries^> >> "%TEMP%\sig_task.xml"
echo     ^<ExecutionTimeLimit^>PT0S^</ExecutionTimeLimit^> >> "%TEMP%\sig_task.xml"
echo     ^<RestartOnFailure^> >> "%TEMP%\sig_task.xml"
echo       ^<Interval^>PT1M^</Interval^> >> "%TEMP%\sig_task.xml"
echo       ^<Count^>999^</Count^> >> "%TEMP%\sig_task.xml"
echo     ^</RestartOnFailure^> >> "%TEMP%\sig_task.xml"
echo     ^<AllowStartOnDemand^>true^</AllowStartOnDemand^> >> "%TEMP%\sig_task.xml"
echo     ^<Enabled^>true^</Enabled^> >> "%TEMP%\sig_task.xml"
echo   ^</Settings^> >> "%TEMP%\sig_task.xml"
echo   ^<Actions Context="Author"^> >> "%TEMP%\sig_task.xml"
echo     ^<Exec^> >> "%TEMP%\sig_task.xml"
echo       ^<Command^>%WAITRESS%^</Command^> >> "%TEMP%\sig_task.xml"
echo       ^<Arguments^>%ARGS%^</Arguments^> >> "%TEMP%\sig_task.xml"
echo       ^<WorkingDirectory^>%APP_DIR%^</WorkingDirectory^> >> "%TEMP%\sig_task.xml"
echo     ^</Exec^> >> "%TEMP%\sig_task.xml"
echo   ^</Actions^> >> "%TEMP%\sig_task.xml"
echo ^</Task^> >> "%TEMP%\sig_task.xml"

REM --- Registrar con XML completo ---
schtasks /delete /tn "%TAREA%" /f 2>nul
schtasks /create /tn "%TAREA%" /xml "%TEMP%\sig_task.xml" /f

echo.
echo [OK] Tarea programada creada correctamente.
echo.
echo Caracteristicas:
echo   - Inicia automaticamente al encender el equipo (30s de delay)
echo   - Se reinicia automaticamente si falla (cada 1 minuto)
echo   - Corre como SYSTEM (no necesita usuario logueado)
echo   - Sin limite de tiempo de ejecucion
echo.
echo Comandos utiles:
echo   Iniciar ahora:  schtasks /run /tn %TAREA%
echo   Detener:         schtasks /end /tn %TAREA%
echo   Ver estado:      schtasks /query /tn %TAREA%
echo   Eliminar:        schtasks /delete /tn %TAREA% /f
echo.

REM --- Iniciar la tarea ahora ---
echo Iniciando servidor...
schtasks /run /tn "%TAREA%"

echo.
echo ==========================================
echo   Servidor accesible en:
echo   http://172.16.0.13:8000
echo ==========================================
echo.
pause
