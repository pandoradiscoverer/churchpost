@echo off
REM Controllo Python
where python >nul 2>nul
if %ERRORLEVEL% neq 0 (
    echo Python non trovato. Scarico e installo Python...
    powershell -Command "Start-Process 'https://www.python.org/ftp/python/3.11.8/python-3.11.8-amd64.exe' -Wait"
    echo Dopo l'installazione, aggiungi Python al PATH e riavvia questo script.
    pause
    exit /b
) else (
    echo Python trovato.
    for /f "delims=" %%i in ('where python') do set PYTHONPATH=%%~dpi
    set PYTHONPATH=%PYTHONPATH:~0,-1%
    setx PATH "%PATH%;%PYTHONPATH%"
    echo Python aggiunto al PATH.
)

REM Controllo ffmpeg
if not exist C:\ffmpeg\bin\ffmpeg.exe (
    echo ffmpeg non trovato. Scarico e installo ffmpeg in C:\ffmpeg...
    if not exist C:\ffmpeg mkdir C:\ffmpeg
    powershell -Command "Invoke-WebRequest -Uri 'https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip' -OutFile 'ffmpeg.zip'"
    powershell -Command "Expand-Archive -Path 'ffmpeg.zip' -DestinationPath 'C:\'"
    for /d %%i in (C:\ffmpeg-*) do move "%%i" "C:\ffmpeg"
    setx PATH "%PATH%;C:\ffmpeg\bin"
    echo ffmpeg installato in C:\ffmpeg e aggiunto al PATH.
) else (
    echo ffmpeg trovato in C:\ffmpeg.
)

REM Crea virtual environment churchpost
python -m venv churchpost

REM Attiva environment e installa requirements
call churchpost\Scripts\activate.bat
pip install --upgrade pip
if exist requirements.txt (
    pip install -r requirements.txt
) else (
    echo requirements.txt non trovato!
)

echo Installazione completata.
pause
