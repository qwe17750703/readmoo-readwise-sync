@echo off
REM Windows Task Scheduler 的進入點，無互動執行
cd /d "%~dp0"
python main.py --silent
exit /b %ERRORLEVEL%
