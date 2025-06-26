#!/bin/bash
# Script di avvio churchpost
set -e
source venv/bin/activate
trap 'deactivate; echo "\n[INFO] Environment disattivato."' EXIT

echo "Premi CTRL+C per chiudere l'applicazione."
python app.py
