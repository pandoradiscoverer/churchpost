from flask import Flask, render_template, request, jsonify, send_file
import openai
import os
import tempfile
import uuid
from datetime import datetime
from waitress import serve
import json
from werkzeug.utils import secure_filename
import yt_dlp
import subprocess
import re
from urllib.parse import urlparse, parse_qs

app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 25 * 1024 * 1024  # 25MB max file size (Whisper limit)
app.config['UPLOAD_FOLDER'] = 'temp_uploads'
app.config['YOUTUBE_FOLDER'] = 'youtube_downloads'

# Assicurati che le directory esistano
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
os.makedirs(app.config['YOUTUBE_FOLDER'], exist_ok=True)

# Formati audio supportati da OpenAI Whisper
ALLOWED_EXTENSIONS = {'wav', 'mp3', 'm4a', 'mp4', 'mpeg', 'mpga', 'webm', 'flac'}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def parse_time_to_seconds(time_str):
    """Converte formato hhmmss o hh:mm:ss in secondi"""
    if not time_str:
        return 0
    
    # Rimuovi spazi e caratteri non numerici eccetto :
    time_str = re.sub(r'[^\d:]', '', time_str)
    
    # Se formato hhmmss (6 cifre)
    if len(time_str) == 6 and ':' not in time_str:
        hours = int(time_str[:2])
        minutes = int(time_str[2:4])
        seconds = int(time_str[4:6])
    # Se formato hh:mm:ss
    elif ':' in time_str:
        parts = time_str.split(':')
        if len(parts) == 3:
            hours, minutes, seconds = map(int, parts)
        elif len(parts) == 2:
            hours = 0
            minutes, seconds = map(int, parts)
        else:
            return 0
    else:
        return 0
    
    return hours * 3600 + minutes * 60 + seconds

def seconds_to_hhmmss(seconds):
    """Converte secondi in formato hh:mm:ss"""
    hours = seconds // 3600
    minutes = (seconds % 3600) // 60
    secs = seconds % 60
    return f"{hours:02d}:{minutes:02d}:{secs:02d}"

def validate_youtube_url(url):
    """Valida URL YouTube e estrae video ID"""
    youtube_regex = re.compile(
        r'(https?://)?(www\.)?(youtube|youtu|youtube-nocookie)\.(com|be)/'
        r'(watch\?v=|embed/|v/|.+\?v=)?([^&=%\?]{11})'
    )
    match = youtube_regex.match(url)
    return match.group(6) if match else None

class TranscriptionService:
    def __init__(self):
        self.api_key = None
        self.client = None
    
    def set_api_key(self, api_key):
        try:
            self.api_key = api_key
            self.client = openai.OpenAI(api_key=api_key)
            # Test della connessione
            self.client.models.list()
            
            # Inizializza anche i generatori
            global facebook_generator, image_generator
            facebook_generator = FacebookPostGenerator(self.client)
            image_generator = ImageGenerator(self.client)
            
            return True, "API Key configurata correttamente"
        except Exception as e:
            return False, f"Errore API Key: {str(e)}"
    
    def transcribe_audio(self, audio_file_path, language="it"):
        if not self.client:
            return False, "API Key non configurata"
        
        try:
            # Verifica dimensioni file (max 25MB per Whisper)
            file_size = os.path.getsize(audio_file_path)
            if file_size > 25 * 1024 * 1024:
                return False, "File troppo grande per Whisper API (max 25MB)"
            
            with open(audio_file_path, "rb") as audio_file:
                transcript = self.client.audio.transcriptions.create(
                    model="whisper-1",  # Nuovo modello 2025 - migliore e più economico
                    file=audio_file,
                    language=language if language != "auto" else None,
                    response_format="text"  # Formato compatibile con gpt-4o-mini-transcribe
                )
            
            # Estrai il testo dalla risposta
            text = transcript if isinstance(transcript, str) else str(transcript)
            return True, text
            
        except Exception as e:
            error_msg = str(e)
            if "file size" in error_msg.lower():
                return False, "File troppo grande. OpenAI Whisper accetta max 25MB"
            elif "invalid file format" in error_msg.lower():
                return False, "Formato file non supportato da Whisper"
            else:
                return False, f"Errore nella trascrizione: {error_msg}"

class YouTubeProcessor:
    def __init__(self):
        self.download_folder = app.config['YOUTUBE_FOLDER']
    
    def get_video_info(self, url):
        """Ottiene informazioni sul video YouTube"""
        try:
            ydl_opts = {
                'quiet': True,
                'no_warnings': True,
            }
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=False)
                return {
                    'title': info.get('title', 'Unknown'),
                    'duration': info.get('duration', 0),
                    'uploader': info.get('uploader', 'Unknown'),
                    'view_count': info.get('view_count', 0)
                }
        except Exception as e:
            return None
    
    def download_and_extract_segment(self, url, start_time, end_time, language="it"):
        """Scarica e estrae segmento audio da YouTube"""
        try:
            start_seconds = parse_time_to_seconds(start_time)
            end_seconds = parse_time_to_seconds(end_time)
            
            if end_seconds <= start_seconds:
                return False, "Tempo di fine deve essere maggiore del tempo di inizio"
            
            duration = end_seconds - start_seconds
            if duration > 3600:  # Max 1 ora
                return False, "Segmento troppo lungo (max 1 ora)"
            
            # Genera nomi file unici
            unique_id = str(uuid.uuid4())
            temp_audio = os.path.join(self.download_folder, f"{unique_id}_temp.%(ext)s")
            final_audio = os.path.join(self.download_folder, f"{unique_id}_final.mp3")
            
            # Calcola bitrate ottimale per rimanere sotto i 25MB
            target_size_mb = 23  # Margine di sicurezza
            target_size_bytes = target_size_mb * 1024 * 1024
            bitrate = min(128, max(32, (target_size_bytes * 8) // (duration * 1000)))
            
            # Configurazione yt-dlp per scaricare solo audio
            ydl_opts = {
                'format': 'worstaudio/worst',
                'outtmpl': temp_audio,
                'quiet': True,
                'no_warnings': True,
            }
            
            # Scarica il video
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([url])
            
            # Trova il file scaricato
            downloaded_files = [f for f in os.listdir(self.download_folder) if f.startswith(f"{unique_id}_temp")]
            if not downloaded_files:
                return False, "Errore nel download del video"
            
            downloaded_file = os.path.join(self.download_folder, downloaded_files[0])
            
            # Estrai segmento e converti in MP3 con ffmpeg
            ffmpeg_cmd = [
                'ffmpeg', '-y',
                '-ss', str(start_seconds),
                '-i', downloaded_file,
                '-t', str(duration),
                '-acodec', 'mp3',
                '-ab', f'{bitrate}k',
                '-ac', '1',  # Mono per risparmiare spazio
                '-ar', '22050',  # Sample rate ridotto ma sufficiente per speech
                final_audio
            ]
            
            result = subprocess.run(ffmpeg_cmd, capture_output=True, text=True)
            
            # Rimuovi file temporaneo
            if os.path.exists(downloaded_file):
                os.remove(downloaded_file)
            
            if result.returncode != 0:
                return False, f"Errore nella conversione audio: {result.stderr}"
            
            # Verifica dimensioni file finale
            if os.path.exists(final_audio):
                file_size = os.path.getsize(final_audio)
                if file_size > 25 * 1024 * 1024:
                    os.remove(final_audio)
                    return False, "File risultante troppo grande, riduci la durata del segmento"
                
                return True, {
                    'file_path': final_audio,
                    'file_size': file_size,
                    'duration': duration,
                    'bitrate': bitrate,
                    'start_time': seconds_to_hhmmss(start_seconds),
                    'end_time': seconds_to_hhmmss(end_seconds)
                }
            else:
                return False, "Errore nella creazione del file audio"
                
        except Exception as e:
            return False, f"Errore nell'elaborazione: {str(e)}"
    
    def cleanup_old_files(self):
        """Pulisce file più vecchi di 1 ora"""
        try:
            current_time = datetime.now().timestamp()
            for filename in os.listdir(self.download_folder):
                filepath = os.path.join(self.download_folder, filename)
                if os.path.isfile(filepath):
                    file_time = os.path.getctime(filepath)
                    if current_time - file_time > 3600:  # 1 ora
                        os.remove(filepath)
        except Exception:
            pass

class FacebookPostGenerator:
    def __init__(self, openai_client):
        self.client = openai_client

    def generate_facebook_post(self, transcribed_text, topic_hint=""):
        """Genera un post Facebook ottimizzato dal testo trascritto"""
        try:
            # Prompt specifico per post Facebook con le nuove linee guida
            system_prompt = """Sei un esperto copywriter specializzato in content marketing per Facebook, con focus su contenuti spirituali e motivazionali.
Il tuo compito è trasformare trascrizioni audio in post Facebook coinvolgenti e ottimizzati.

REGOLE FONDAMENTALI:
- Lunghezza: 300-400 parole MASSIMO (oltre si rischia lo skip)
- Struttura: paragrafi brevi di 2-4 righe MAX
- Inizia SEMPRE con una frase d'impatto (domanda provocatoria, citazione potente, o affermazione che cattura)
- Seleziona solo 1-3 concetti FORTI dalla trascrizione - quelli che bucano
- Usa emoji strategici per guidare l'occhio (non esagerare)
- Linguaggio diretto e conversazionale

STRUTTURA RICHIESTA:

🔥 [FRASE D'IMPATTO INIZIALE - max 2 righe]
[emoji se appropriata]

[PARAGRAFO 1 - max 3-4 righe]
Introduce il primo concetto chiave in modo coinvolgente.

[PARAGRAFO 2 - max 3-4 righe]  
Sviluppa il concetto con esempio concreto o storia.

[PARAGRAFO 3 - max 3-4 righe]
Secondo concetto forte o approfondimento.

[PARAGRAFO 4 - max 3-4 righe]
Terzo concetto o applicazione pratica.

✨ [DOMANDA FINALE DI RIFLESSIONE]
Una domanda che stimoli commenti e interazione.

#hashtag1 #hashtag2 #hashtag3 (8-10 hashtag pertinenti)

IMPORTANTE:
- NON superare 400 parole totali
- Ogni paragrafo DEVE essere separato da una riga vuota
- Usa **grassetto** per 2-3 parole chiave nel testo
- Le emoji devono essere pertinenti, non decorative
- La domanda finale deve essere profonda ma accessibile"""

            user_prompt = f"""Trascrizione da elaborare:
{transcribed_text}

{f'Argomento/Contesto: {topic_hint}' if topic_hint else ''}

RICORDA: 
- MAX 400 parole totali
- Paragrafi di 2-4 righe
- Inizia con frase d'impatto
- Solo 1-3 concetti che bucano
- Chiudi con domanda di riflessione

Crea il post seguendo ESATTAMENTE la struttura richiesta."""

            response = self.client.chat.completions.create(
                model="gpt-4.5-preview",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                max_tokens=1000,
                temperature=0.8,
                presence_penalty=0.2,
                frequency_penalty=0.2
            )

            post_content = response.choices[0].message.content

            word_count = len(post_content.split())
            if word_count > 450:
                words = post_content.split()[:400]
                post_content = ' '.join(words) + "\n\n[Post abbreviato per ottimizzare l'engagement]"

            return True, post_content

        except Exception as e:
            return False, f"Errore nella generazione del post: {str(e)}"

# in app.py
# Sostituisca l'INTERA classe ImageGenerator con questa versione aggiornata

class ImageGenerator:
    def __init__(self, openai_client):
        self.client = openai_client

    def generate_image_from_summary(self, facebook_post_text):
        try:
            prompt_response = self.client.chat.completions.create(
                model="gpt-4.5-preview",
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "Riceverai il testo di un post Facebook. "+
                            "Estrai SOLO le informazioni essenziali per generare un prompt di immagine compatto seguendo questa pipeline: "
                            "[Soggetto + dettagli] + [Azione/Posa] + [Ambiente/Contesto] + [Illuminazione] + [Dettagli fotocamera] + stile artistico. "
                            "Lo stile deve essere sempre: colori vividi, ampie pennellate, nessun fronzolo, nessun elemento allucinato, nessun testo, nessun riferimento a social o grafica. "
                            "NON generare mai immagini iconografiche di Cristo o del suo volto, né immagini in stile iconografia cattolica. Siamo protestanti e non desideriamo questo tipo di rappresentazione. "
                            "Rispondi SOLO con il prompt finale, senza spiegazioni."
                        )
                    },
                    {
                        "role": "user",
                        "content": facebook_post_text
                    }
                ]
            )
            prompt = prompt_response.choices[0].message.content.strip()
            image_response = self.client.images.generate(
                model="gpt-image-1",
                prompt=prompt,
                n=1,
                size="1024x1536",
                quality="high",
                background="auto",
                output_format="png",
                output_compression=100,
                moderation="auto"
            )
            if (
                image_response
                and hasattr(image_response, "data")
                and isinstance(image_response.data, list)
                and len(image_response.data) > 0
                and hasattr(image_response.data[0], "b64_json")
            ):
                return True, (image_response.data[0].b64_json, prompt)
            else:
                return False, "Risposta inattesa dall'API immagini"
        except Exception as e:
            return False, str(e)

# Istanza globale dei servizi
transcription_service = TranscriptionService()
youtube_processor = YouTubeProcessor()
facebook_generator = None  # Inizializzato quando API key è configurata
image_generator = None     # Inizializzato quando API key è configurata

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/set-api-key', methods=['POST'])
def set_api_key():
    data = request.get_json()
    api_key = data.get('api_key', '').strip()
    
    if not api_key:
        return jsonify({'success': False, 'message': 'API Key richiesta'})
    
    success, message = transcription_service.set_api_key(api_key)
    return jsonify({'success': success, 'message': message})

@app.route('/api/youtube-info', methods=['POST'])
def get_youtube_info():
    data = request.get_json()
    url = data.get('url', '').strip()
    
    if not url:
        return jsonify({'success': False, 'message': 'URL richiesto'})
    
    video_id = validate_youtube_url(url)
    if not video_id:
        return jsonify({'success': False, 'message': 'URL YouTube non valido'})
    
    info = youtube_processor.get_video_info(url)
    if not info:
        return jsonify({'success': False, 'message': 'Impossibile ottenere informazioni video'})
    
    # Converti durata in formato leggibile
    duration_str = seconds_to_hhmmss(info['duration'])
    
    return jsonify({
        'success': True,
        'info': {
            'title': info['title'],
            'duration': duration_str,
            'duration_seconds': info['duration'],
            'uploader': info['uploader'],
            'view_count': info.get('view_count', 0)
        }
    })

@app.route('/api/process-youtube', methods=['POST'])
def process_youtube():
    data = request.get_json()
    url = data.get('url', '').strip()
    start_time = data.get('start_time', '').strip()
    end_time = data.get('end_time', '').strip()
    language = data.get('language', 'it')
    
    if not all([url, start_time, end_time]):
        return jsonify({'success': False, 'message': 'URL, tempo di inizio e fine sono richiesti'})
    
    video_id = validate_youtube_url(url)
    if not video_id:
        return jsonify({'success': False, 'message': 'URL YouTube non valido'})
    
    try:
        # Pulisci file vecchi
        youtube_processor.cleanup_old_files()
        
        # Elabora il video
        success, result = youtube_processor.download_and_extract_segment(
            url, start_time, end_time, language
        )
        
        if not success:
            return jsonify({'success': False, 'message': result})
        
        # Trascrivi l'audio estratto
        audio_file = result['file_path']
        success_transcription, transcription_result = transcription_service.transcribe_audio(
            audio_file, language
        )
        
        # Rimuovi file audio temporaneo
        if os.path.exists(audio_file):
            os.remove(audio_file)
        
        if success_transcription:
            timestamp = datetime.now().strftime("%H:%M:%S")
            file_size_mb = round(result['file_size'] / (1024 * 1024), 2)
            
            return jsonify({
                'success': True,
                'text': transcription_result,
                'timestamp': timestamp,
                'metadata': {
                    'source': 'YouTube',
                    'duration': f"{result['duration']}s",
                    'file_size': f"{file_size_mb} MB",
                    'bitrate': f"{result['bitrate']}k",
                    'segment': f"{result['start_time']} - {result['end_time']}"
                }
            })
        else:
            return jsonify({'success': False, 'message': transcription_result})
            
    except Exception as e:
        return jsonify({'success': False, 'message': f'Errore del server: {str(e)}'})

@app.route('/api/transcribe-file', methods=['POST'])
def transcribe_file():
    if 'audio_file' not in request.files:
        return jsonify({'success': False, 'message': 'Nessun file caricato'})
    
    file = request.files['audio_file']
    language = request.form.get('language', 'it')
    
    if file.filename == '':
        return jsonify({'success': False, 'message': 'Nessun file selezionato'})
    
    if not allowed_file(file.filename):
        return jsonify({'success': False, 'message': f'Formato non supportato. Usa: {", ".join(ALLOWED_EXTENSIONS)}'})
    
    # Controlla dimensioni file prima del salvataggio
    file.seek(0, os.SEEK_END)
    file_size = file.tell()
    file.seek(0)
    
    if file_size > 25 * 1024 * 1024:
        return jsonify({'success': False, 'message': 'File troppo grande (max 25MB per OpenAI Whisper)'})
    
    try:
        # Salva il file temporaneamente
        filename = secure_filename(file.filename)
        unique_filename = f"{uuid.uuid4()}_{filename}"
        file_path = os.path.join(app.config['UPLOAD_FOLDER'], unique_filename)
        file.save(file_path)
        
        # Trascrivi l'audio
        success, result = transcription_service.transcribe_audio(file_path, language)
        
        # Rimuovi il file temporaneo
        os.remove(file_path)
        
        if success:
            timestamp = datetime.now().strftime("%H:%M:%S")
            file_size_mb = round(file_size / (1024 * 1024), 2)
            return jsonify({
                'success': True, 
                'text': result,
                'timestamp': timestamp,
                'filename': filename,
                'file_size': f"{file_size_mb} MB"
            })
        else:
            return jsonify({'success': False, 'message': result})
            
    except Exception as e:
        return jsonify({'success': False, 'message': f'Errore del server: {str(e)}'})

@app.route('/api/generate-facebook-post', methods=['POST'])
def generate_facebook_post():
    if not facebook_generator:
        return jsonify({'success': False, 'message': 'API Key OpenAI non configurata'})
    
    data = request.get_json()
    text = data.get('text', '').strip()
    topic_hint = data.get('topic_hint', '').strip()
    youtube_url = data.get('youtube_url', '').strip() if 'youtube_url' in data else None
    youtube_start = data.get('youtube_start', '').strip() if 'youtube_start' in data else None
    
    if not text:
        return jsonify({'success': False, 'message': 'Testo richiesto per generare il post'})
    
    try:
        success, result = facebook_generator.generate_facebook_post(text, topic_hint)
        
        if success:
            # Se presenti, aggiungi il link YouTube in coda
            if youtube_url and youtube_start:
                def parse_time_to_seconds(time_str):
                    import re
                    if not time_str:
                        return 0
                    time_str = re.sub(r'[^\d:]', '', time_str)
                    if len(time_str) == 6 and ':' not in time_str:
                        hours = int(time_str[:2])
                        minutes = int(time_str[2:4])
                        seconds = int(time_str[4:6])
                    elif ':' in time_str:
                        parts = time_str.split(':')
                        if len(parts) == 3:
                            hours, minutes, seconds = map(int, parts)
                        elif len(parts) == 2:
                            hours = 0
                            minutes, seconds = map(int, parts)
                        else:
                            return 0
                    else:
                        return 0
                    return hours * 3600 + minutes * 60 + seconds
                t_sec = parse_time_to_seconds(youtube_start)
                sep = '\n\n' if not result.endswith('\n') else '\n'
                result = f"{result}{sep}Clicca sul seguente link per ascoltare la Parola di DIO: {youtube_url}?t={t_sec}"
            return jsonify({
                'success': True,
                'facebook_post': result,
                'timestamp': datetime.now().strftime("%H:%M:%S")
            })
        else:
            return jsonify({'success': False, 'message': result})
            
    except Exception as e:
        return jsonify({'success': False, 'message': f'Errore del server: {str(e)}'})

@app.route('/api/generate-image', methods=['POST'])
def generate_image():
    if not image_generator:
        return jsonify({'success': False, 'message': 'API Key OpenAI non configurata'})
    
    data = request.get_json()
    facebook_post = data.get('facebook_post', '').strip()
    
    if not facebook_post:
        return jsonify({'success': False, 'message': 'Post Facebook richiesto per generare immagine'})
    
    try:
        success, result = image_generator.generate_image_from_summary(facebook_post)
        
        if success:
            b64_img, prompt = result if isinstance(result, tuple) else (result, facebook_post)
            return jsonify({
                "success": True,
                "image_data": {
                    "image_b64": b64_img,
                    "revised_prompt": prompt
                }
            })
        else:
            print("Errore generazione immagine:", result)
            return jsonify({'success': False, 'message': result})
            
    except Exception as e:
        return jsonify({'success': False, 'message': f'Errore del server: {str(e)}'})

@app.route('/api/export-text', methods=['POST'])
def export_text():
    data = request.get_json()
    text = data.get('text', '')
    
    if not text:
        return jsonify({'success': False, 'message': 'Nessun testo da esportare'})
    
    try:
        # Crea un file temporaneo
        temp_file = tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False, encoding='utf-8')
        temp_file.write(text)
        temp_file.close()
        
        return send_file(
            temp_file.name,
            as_attachment=True,
            download_name=f'trascrizione_{datetime.now().strftime("%Y%m%d_%H%M%S")}.txt',
            mimetype='text/plain'
        )
    except Exception as e:
        return jsonify({'success': False, 'message': f'Errore nell\'esportazione: {str(e)}'})

@app.errorhandler(413)
def too_large(e):
    return jsonify({'success': False, 'message': 'File troppo grande (max 25MB per OpenAI Whisper)'}), 413

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    print(f"🚀 Avvio server Speech-to-Text su http://localhost:{port}")
    print("📝 Accedi all'applicazione tramite browser")
    import webbrowser
    import threading
    import time
    import shutil
    def open_browser():
        time.sleep(1)
        url = f"http://localhost:{port}"
        chrome_paths = [
            shutil.which('chrome'),
            shutil.which('google-chrome'),
            shutil.which('chromium'),
            shutil.which('chromium-browser'),
            r"C:\Program Files\Google\Chrome\Application\chrome.exe",
            r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"
        ]
        chrome_path = next((p for p in chrome_paths if p and os.path.exists(p)), None)
        if chrome_path:
            import subprocess
            try:
                subprocess.Popen([chrome_path, f'--app={url}', '--new-window'])
                return
            except Exception:
                pass
        # Fallback browser predefinito
        webbrowser.open_new(url)
    threading.Thread(target=open_browser).start()
    # Usa Waitress per servire l'applicazione
    serve(app, host='0.0.0.0', port=port, threads=4)
