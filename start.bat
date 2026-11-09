@echo off
rem Fog Translate starten. Beim ersten Mal wird .venv angelegt und requirements.txt installiert.
setlocal
cd /d "%~dp0"
if exist ".venv\Scripts\pythonw.exe" goto :run
set "PY="
py -3.14 -c "" >nul 2>&1 && set "PY=py -3.14" && goto :found
py -3.13 -c "" >nul 2>&1 && set "PY=py -3.13" && goto :found
py -3.12 -c "" >nul 2>&1 && set "PY=py -3.12" && goto :found
echo Python 3.12 bis 3.14 nicht gefunden. Bitte von python.org installieren.
pause
exit /b 1
:found
echo Richte Fog Translate ein ...
%PY% -m venv .venv || goto :fail
".venv\Scripts\python.exe" -m pip install --isolated --index-url https://pypi.org/simple --require-hashes --only-binary=:all: -r requirements.txt || goto :fail
:run
start "" ".venv\Scripts\pythonw.exe" -m fogtranslate
exit /b 0
:fail
if exist .venv rmdir /s /q .venv
echo Einrichtung fehlgeschlagen.
pause
exit /b 1
