@echo off
cd /d "%~dp0"
git add bot.log
git diff --cached --quiet && exit /b 0
git commit -m "log: auto update %date% %time%"
git push
