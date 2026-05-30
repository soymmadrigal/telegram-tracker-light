@echo off
cd /d "%~dp0\.."
where python >nul 2>nul
if %errorlevel%==0 (
  python app.py
  goto :end
)
where py >nul 2>nul
if %errorlevel%==0 (
  py app.py
  goto :end
)
echo No se encontro Python. Instala Python 3 desde https://www.python.org/downloads/
pause
:end
