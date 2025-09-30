from flask import Flask, request, render_template, redirect, url_for, session, jsonify, send_from_directory
from flask_cors import CORS
from deep_translator import GoogleTranslator
from datetime import datetime
import logging
import re
import sqlite3
import os
from transformers import AutoTokenizer, AutoModelForSeq2SeqLM, pipeline
import torch

# Import auth blueprint
from auth import bp as auth_bp

# ------------------- APP SETUP -------------------
app = Flask(__name__)
CORS(app)
app.secret_key = "translatechatsecret"
app.config['PERMANENT_SESSION_LIFETIME'] = 3600

# Logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

# Register auth blueprint
app.register_blueprint(auth_bp)

# ------------------- DATABASE SETUP -------------------
DB_FILE = "chat.db"
UPLOAD_FOLDER = "uploads"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER 


def init_db():
    """Initialize the database with required tables"""
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    
    # Users table (for future authentication)
    c.execute("""
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE NOT NULL,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
    )
    """)
    
    # Messages table
    c.execute("""
    CREATE TABLE IF NOT EXISTS messages (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT NOT NULL,
        original_content TEXT NOT NULL,
        msg_type TEXT DEFAULT 'text',
        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
    )
    """)
    
    conn.commit()
    conn.close()

# Initialize database when app starts
init_db()

# ------------------- DATABASE HELPER FUNCTIONS -------------------
def save_message(username, content, msg_type="text"):
    """Save a message to the database"""
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    
    c.execute("""
        INSERT INTO messages (username, original_content, msg_type) 
        VALUES (?, ?, ?)
    """, (username, content, msg_type))
    
    conn.commit()
    conn.close()
    logger.debug(f"Message saved to DB: {username} - {content[:50]}...")

def get_recent_messages(limit=100):
    """Get recent messages from database"""
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    
    c.execute("""
        SELECT username, original_content, msg_type, timestamp 
        FROM messages 
        ORDER BY timestamp ASC 
        LIMIT ?
    """, (limit,))
    
    rows = c.fetchall()
    conn.close()
    
    messages = []
    for username, content, msg_type, timestamp in rows:
        messages.append({
            "from": username,
            "original": content,
            "msg_type": msg_type,
            "timestamp": timestamp
        })
    
    return messages

def clear_all_messages():
    """Clear all messages from database"""
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    
    c.execute("DELETE FROM messages")
    conn.commit()
    conn.close()
    logger.debug("All messages cleared from database")

# ------------------- ABBREVIATION & CORRECTION -------------------
from abbreviations import abbreviations
from pattern_expansions import pattern_expansions

def expand_abbreviations(text):
    def replacer(match):
        word = match.group(0)
        key = re.sub(r'\W+', '', word.lower())
        punct = ''.join(re.findall(r'\W+', word))
        if key in abbreviations:
            return abbreviations[key] + punct
        for pattern, replacement in pattern_expansions.items():
            if re.fullmatch(pattern, key):
                return replacement + punct
        return word
    return re.sub(r'\b\w+\W*', replacer, text)

# Load AI correction model
model_name = "oliverguhr/spelling-correction-english-base"
tokenizer = AutoTokenizer.from_pretrained(model_name)
model = AutoModelForSeq2SeqLM.from_pretrained(model_name)
corrector = pipeline("text2text-generation", model=model, tokenizer=tokenizer)

def correct_text(text):
    result = corrector(text, max_length=256, clean_up_tokenization_spaces=True)
    return result[0]['generated_text']

# ------------------- CHAT ROUTES -------------------

@app.route("/chat")
def chat():
    if "username" not in session:
        return redirect(url_for("auth.login_page"))  # redirect to login if not logged in
    return render_template("chat.html", 
                           username=session["username"],
                           lang=session.get("lang", "en"))

@app.route("/send", methods=["POST"])
def send_message():
    try:
        data = request.get_json()
        if not data:
            return jsonify({"status": "error", "message": "No data provided"}), 400

        sender = data.get("from", "Anonymous")
        raw_text = data.get("text", "").strip()
        
        if not raw_text:
            return jsonify({"status": "error", "message": "Empty message"}), 400

        # Process text: expand abbreviations and correct spelling
        expanded_text = expand_abbreviations(raw_text)
        corrected_text = correct_text(expanded_text)
        final_text = corrected_text

        # Save to database
        save_message(sender, final_text, "text")
        
        logger.debug(f"New message stored in DB: {sender} - {final_text[:50]}...")
        return jsonify({"status": "ok"})

    except Exception as e:
        logger.error(f"Error in send_message: {str(e)}")
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route("/messages")
def get_messages():
    try:
        user_lang = request.args.get('lang', 'en')
        current_user = request.args.get('user', 'Anonymous')
        
        # Get messages from database
        db_messages = get_recent_messages(100)
        translated_messages = []

        for msg in db_messages:
            original = msg.get("original", "")
            sender = msg.get("from", "Unknown")
            msg_type = msg.get("msg_type", "text")

            # For text messages, translate if needed
            if msg_type == "text":
                if sender == current_user:
                    translated = original
                else:
                    try:
                        translated = GoogleTranslator(source='auto', target=user_lang).translate(original[:5000])
                    except Exception as e:
                        logger.warning(f"Translation failed: {e}")
                        translated = original
                content = translated
            else:
                # For images, just use the URL
                content = original

            translated_messages.append({
                "from": sender,
                "content": content,
                "msg_type": msg_type,
                "timestamp": msg.get("timestamp")
            })

        return jsonify({"messages": translated_messages})

    except Exception as e:
        logger.error(f"Error in get_messages: {str(e)}")
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route("/clear", methods=["POST"])
def clear_messages():
    clear_all_messages()
    logger.debug("All messages cleared from database")
    return jsonify({"status": "cleared"})

@app.route("/upload_image", methods=["POST"])
def upload_image():
    try:
        if "image" not in request.files:
            return jsonify({"status": "error", "message": "No file"}), 400
        
        file = request.files["image"]
        if file.filename == "":
            return jsonify({"status": "error", "message": "Empty filename"}), 400

        # Get username from session or form data
        username = session.get("username") or request.form.get("username", "Anonymous")
        
        # Secure filename and save
        filename = f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{file.filename}"
        filepath = os.path.join(UPLOAD_FOLDER, filename)
        file.save(filepath)

        # Save image URL to database
        img_url = f"/uploads/{filename}"
        save_message(username, img_url, "image")

        return jsonify({"status": "ok", "url": img_url})

    except Exception as e:
        logger.error(f"Error in upload_image: {str(e)}")
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/uploads/<filename>')
def uploaded_file(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

@app.route("/upload_audio", methods=["POST"])
def upload_audio():
    try:
        if "audio" not in request.files:
            return jsonify({"status": "error", "message": "No file"}), 400
        
        file = request.files["audio"]
        if file.filename == "":
            return jsonify({"status": "error", "message": "Empty filename"}), 400

        username = session.get("username") or request.form.get("username", "Anonymous")

        filename = f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{file.filename}"
        filepath = os.path.join(UPLOAD_FOLDER, filename)
        file.save(filepath)

        # Save audio URL in DB
        audio_url = f"/uploads/{filename}"
        save_message(username, audio_url, "audio")

        return jsonify({"status": "ok", "url": audio_url})

    except Exception as e:
        logger.error(f"Error in upload_audio: {str(e)}")
        return jsonify({"status": "error", "message": str(e)}), 500



# ------------------- RUN APP -------------------
if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5001)