@echo off
rem ============================================================
rem  NFL Matchup Analytics - inicia backend y frontend (desarrollo)
rem  Uso: doble clic en este archivo, o en una terminal:  iniciar.cmd
rem  Para detener: cierra las dos ventanas "NFL backend" y "NFL frontend".
rem ============================================================
setlocal
set "ROOT=%~dp0"
set "ROOT=%ROOT:~0,-1%"
set "PY=%ROOT%\.venv\Scripts\python.exe"
set "NODEDIR=%ROOT%\.hackathon\.tools\node"
set "API_PORT=8000"
set "WEB_PORT=5173"

if not exist "%PY%" (
  echo [ERROR] No existe .venv. Ejecuta primero:  .hackathon\setup.cmd
  pause
  exit /b 1
)
if not exist "%NODEDIR%\npm.cmd" (
  echo [ERROR] No se encontro Node en .hackathon\.tools\node. Ejecuta primero:  .hackathon\setup.cmd
  pause
  exit /b 1
)
if not exist "%ROOT%\dashboard\node_modules" (
  echo [ERROR] Faltan las dependencias del dashboard. Ejecuta primero:  .hackathon\setup.cmd
  pause
  exit /b 1
)
dir /s /b "%ROOT%\data\games.csv" >nul 2>&1
if errorlevel 1 (
  echo [ERROR] No se encontraron los datos en data\. Consulta la seccion "Datos" del README.md
  pause
  exit /b 1
)

echo Iniciando backend en http://localhost:%API_PORT% ...
start "NFL backend" /d "%ROOT%" cmd /k ""%PY%" -m uvicorn backend.main:app --port %API_PORT%"

echo Iniciando frontend en http://localhost:%WEB_PORT% ...
start "NFL frontend" /d "%ROOT%\dashboard" cmd /k "set "PATH=%NODEDIR%;%PATH%" && npm.cmd run dev -- --port %WEB_PORT% --strictPort"

echo Esperando a que el backend responda...
set /a INTENTOS=0
:espera
set /a INTENTOS+=1
curl.exe -s -o nul -f "http://localhost:%API_PORT%/health" >nul 2>&1
if not errorlevel 1 goto listo
if %INTENTOS% geq 60 (
  echo [AVISO] El backend no respondio en 60 s. Revisa la ventana "NFL backend".
  goto abrir
)
timeout /t 1 /nobreak >nul
goto espera

:listo
echo Backend listo. Los datos se procesan en segundo plano (20-30 s); la app muestra el progreso.

:abrir
timeout /t 3 /nobreak >nul
start "" "http://localhost:%WEB_PORT%/"
echo.
echo Aplicacion:  http://localhost:%WEB_PORT%/
echo API:         http://localhost:%API_PORT%/health
echo Para detenerla, cierra las ventanas "NFL backend" y "NFL frontend".
endlocal
