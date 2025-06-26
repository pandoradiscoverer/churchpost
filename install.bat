@echo off
REM Script di installazione churchpost - Verbose

REM Controllo Python
where python >nul 2>nul
if %ERRORLEVEL% neq 0 (
    echo [INFO] Python non trovato. Scarico e installo Python...
    powershell -Command "Start-Process 'https://www.python.org/ftp/python/3.11.8/python-3.11.8-amd64.exe' -Wait"
    echo [INFO] Dopo l'installazione, aggiungi Python al PATH e riavvia questo script.
    pause
    exit /b
) else (
    echo [INFO] Python trovato.
    for /f "delims=" %%i in ('where python') do set PYTHONPATH=%%~dpi
    set PYTHONPATH=%PYTHONPATH:~0,-1%
    setx PATH "%PATH%;%PYTHONPATH%"
    echo [INFO] Python aggiunto al PATH temporaneamente.
)

REM Controllo ffmpeg
set "FFMPEG_BIN_PATH="
if not exist C:\ffmpeg (
    echo [INFO] C:\ffmpeg non esiste. Creo la cartella...
    mkdir C:\ffmpeg
)
if not exist C:\ffmpeg\bin\ffmpeg.exe (
    echo [INFO] ffmpeg non trovato. Scarico e installo ffmpeg in C:\ffmpeg...
    echo [INFO] Download di ffmpeg in corso...
    powershell -Command "Invoke-WebRequest -Uri 'https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip' -OutFile 'C:\ffmpeg\ffmpeg.zip'"
    echo [INFO] Estrazione dell'archivio...
    powershell -Command "Expand-Archive -Path 'C:\ffmpeg\ffmpeg.zip' -DestinationPath 'C:\ffmpeg'"
    del C:\ffmpeg\ffmpeg.zip
    echo [INFO] Ricerca della cartella bin all'interno di C:\ffmpeg..."
    for /d %%i in (C:\ffmpeg\ffmpeg-*) do (
        if exist "%%i\bin\ffmpeg.exe" (
            set "FFMPEG_BIN_PATH=%%i\bin"
            echo [INFO] Trovata cartella bin: %%i\bin
            xcopy /E /I /Y "%%i\bin" "C:\ffmpeg\bin"
            echo [INFO] Copiata cartella bin in C:\ffmpeg\bin
            rd /s /q "%%i"
        )
    )
) else (
    echo [INFO] ffmpeg trovato in C:\ffmpeg.
)

REM Imposta il PATH con la cartella bin trovata
if exist C:\ffmpeg\bin\ffmpeg.exe (
    setx PATH "%PATH%;C:\ffmpeg\bin"
    echo [INFO] ffmpeg aggiunto al PATH: C:\ffmpeg\bin
) else (
    echo [ERRORE] ffmpeg non trovato! Controlla l'installazione.
)

REM Crea virtual environment churchpost
if exist churchpost (
    echo [INFO] Virtual environment churchpost gia' presente.
) else (
    echo [INFO] Creo virtual environment churchpost...
    python -m venv churchpost
)

REM Attiva environment e installa requirements
call churchpost\Scripts\activate.bat
if %ERRORLEVEL% neq 0 (
    echo [ERRORE] Impossibile attivare l'environment churchpost.
    pause
    exit /b
)
echo [INFO] Aggiorno pip...
pip install --upgrade pip
if exist requirements.txt (
    echo [INFO] Installo i pacchetti da requirements.txt...
    pip install -r requirements.txt
) else (
    echo [ATTENZIONE] requirements.txt non trovato!
)

REM Disattiva environment
call churchpost\Scripts\deactivate.bat


echo [INFO] Installazione completata. Puoi chiudere questa finestra.
pause
