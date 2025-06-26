#!/bin/bash
# Script di installazione churchpost - Verbose
set -e

# Controllo Python
if ! command -v python3 &> /dev/null; then
    echo "[INFO] Python3 non trovato. Installalo manualmente e riprova."
    exit 1
else
    echo "[INFO] Python3 trovato: $(python3 --version)"
fi

# Controllo ffmpeg
if ! command -v ffmpeg &> /dev/null; then
    echo "[INFO] ffmpeg non trovato. Provo a installare..."
    if [[ "$OSTYPE" == "linux-gnu"* ]]; then
        sudo apt update && sudo apt install -y ffmpeg
    elif [[ "$OSTYPE" == "darwin"* ]]; then
        brew install ffmpeg
    else
        echo "[ERRORE] Sistema non supportato per installazione automatica di ffmpeg."
        exit 1
    fi
else
    echo "[INFO] ffmpeg trovato: $(ffmpeg -version | head -n 1)"
fi

# Crea virtual environment churchpost
if [ ! -d "venv" ]; then
    echo "[INFO] Creo virtual environment churchpost..."
    python3 -m venv venv
else
    echo "[INFO] Virtual environment churchpost già presente."
fi

# Attiva environment e installa requirements
source venv/bin/activate
echo "[INFO] Aggiorno pip..."
pip install --upgrade pip
if [ -f requirements.txt ]; then
    echo "[INFO] Installo i pacchetti da requirements.txt..."
    pip install -r requirements.txt
else
    echo "[ATTENZIONE] requirements.txt non trovato!"
fi

deactivate
echo "[INFO] Installazione completata. Puoi chiudere questa finestra."
