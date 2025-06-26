@echo off
call churchpost\Scripts\activate.bat
echo Premi CTRL+C per chiudere l'applicazione.
:run
python app.py
if %ERRORLEVEL%==0 goto end
REM Se l'utente preme CTRL+C, python restituisce errorlevel 1
:end
call churchpost\Scripts\deactivate.bat
pause
