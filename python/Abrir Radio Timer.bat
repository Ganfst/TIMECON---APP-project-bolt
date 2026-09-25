@echo off
rem Abre Radio Timer sin dejar una consola abierta. Se puede ejecutar con doble clic.
cd /d "%~dp0"
where pythonw >nul 2>nul
if %errorlevel%==0 (
    start "" pythonw run.py %*
) else (
    start "" python run.py %*
)
