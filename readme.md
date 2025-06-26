# Speech-to-Text YouTube & Facebook Post Generator

## 🚀 Funzionalità principali

- **Trascrizione audio**: Carica file audio o estrai segmenti da YouTube, trascrivi in testo con OpenAI Whisper.
- **Generazione post Facebook**: Trasforma la trascrizione in un post ottimizzato per Facebook con GPT-4.5-preview.
- **Generazione immagini AI**: Crea immagini evocative per il post tramite GPT-4.5-preview + gpt-image-1 (output base64, nessun prompt mostrato all'utente).
- **Download e copia**: Scarica testo, copia post, scarica immagini generate.
- **Automazione Windows**: Script install.bat e run.bat per setup e avvio automatico (inclusa installazione Python, ffmpeg, environment churchpost).
- **Supporto multi-lingua**: Scegli la lingua della trascrizione.
- **Gestione segmenti YouTube**: Estrai e trascrivi solo la parte desiderata del video.
- **Limiti automatici**: Segmento max 1 ora, file max 25MB, ottimizzazione bitrate.
- **Interfaccia web moderna**: UI responsive, modale preview, download diretto immagini base64.

## ⚡ Installazione Rapida

### Windows
```bat
install.bat
run.bat
```

### macOS/Linux
```bash
chmod +x install.sh
./install.sh
source venv/bin/activate
python app.py
```

## 📁 File Necessari

```
project/
├── app.py
├── requirements.txt
├── templates/
│   └── index.html
├── install.bat
├── run.bat
├── install.sh (opzionale)
├── README.md
├── LICENSE
├── CONTRIBUTING.md
└── .gitignore
```

## 🔧 Prerequisiti
- Python 3.8+
- FFmpeg
- API Key OpenAI

## 🎯 Utilizzo
1. Avvia app: `run.bat` (Windows) o `python app.py`
2. Apri browser: `http://localhost:5000`
3. Inserisci API Key OpenAI
4. Carica audio o YouTube, genera post e immagine, copia o scarica!

## 🆘 Supporto
Vedi CONTRIBUTING.md o apri una issue.

---

**Happy transcribing & posting! 🎉**