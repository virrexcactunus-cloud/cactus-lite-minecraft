@echo off
chcp 65001 >nul
cd /d "%~dp0"
where pythonw >nul 2>nul && (set PY=pythonw) || (set PY=python)
%PY% -c "import minecraft_launcher_lib, PIL, wx" >nul 2>nul || %PY% -m pip install --quiet -r requirements.txt
start "" %PY% launcher.py
