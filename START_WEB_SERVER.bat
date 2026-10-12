@echo off
cd /d "%~dp0"
where py >nul 2>nul
if errorlevel 1 (python -m pip install -r requirements.txt && python yt.py --server) else (py -3 -m pip install -r requirements.txt && py -3 yt.py --server)
pause
