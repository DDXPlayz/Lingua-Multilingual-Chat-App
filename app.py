from flask import Flask, request, render_template, redirect, url_for, session, jsonify
from flask_cors import CORS
from deep_translator import GoogleTranslator
from datetime import datetime
import logging
import re
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

# ------------------- CHAT MESSAGES -------------------
messages = []

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
        expanded_text = expand_abbreviations(raw_text)
        corrected_text = correct_text(expanded_text)
        text = corrected_text

        if not text:
            return jsonify({"status": "error", "message": "Empty message"}), 400

        new_message = {
            "from": sender,
            "original": text,
            "timestamp": datetime.now().isoformat()
        }
        messages.append(new_message)
        logger.debug(f"New message stored: {new_message}")
        return jsonify({"status": "ok"})

    except Exception as e:
        logger.error(f"Error in send_message: {str(e)}")
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route("/messages")
def get_messages():
    try:
        user_lang = request.args.get('lang', 'en')
        current_user = request.args.get('user', 'Anonymous')
        translated_messages = []

        for msg in messages[-100:]:
            original = msg.get("original", "")
            sender = msg.get("from", "Unknown")

            if sender == current_user:
                translated = original
            else:
                try:
                    translated = GoogleTranslator(source='auto', target=user_lang).translate(original[:5000])
                except Exception:
                    translated = original

            translated_messages.append({
                "from": sender,
                "content": translated,
                "timestamp": msg.get("timestamp")
            })

        return jsonify({"messages": translated_messages})

    except Exception as e:
        logger.error(f"Error in get_messages: {str(e)}")
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route("/clear", methods=["POST"])
def clear_messages():
    global messages
    messages = []
    logger.debug("All messages cleared")
    return jsonify({"status": "cleared"})

# ------------------- RUN APP -------------------
if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5001)
