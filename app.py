from flask import Flask, request, render_template, redirect, url_for, session, jsonify
from flask_cors import CORS
from deep_translator import GoogleTranslator
from datetime import datetime
import logging

app = Flask(__name__)
CORS(app)
app.secret_key = "translatechatsecret"
app.config['PERMANENT_SESSION_LIFETIME'] = 3600  # 1 hour session lifetime

# Configure logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

# Store messages with timestamp
messages = []

@app.route('/', methods=["GET"])
def login():
    """Handle login/initial page"""
    session.clear()
    return render_template("index.html")

@app.route('/chat', methods=["POST", "GET"])
def chat():
    """Handle chat room entry"""
    if request.method == "POST":
        session.permanent = True
        username = request.form.get('username', '').strip()
        session['username'] = username if username else 'Anonymous'
        session['lang'] = request.form.get('lang', 'en')
        logger.debug(f"New session: {session['username']} ({session['lang']})")
        return redirect(url_for('chat'))
    
    if 'username' not in session:
        return redirect(url_for('login'))
    
    return render_template("chat.html", 
                         username=session['username'],
                         lang=session['lang'])


import re
from abbreviations import abbreviations  # ← importing your dictionary
from pattern_expansions import pattern_expansions  # ← importing your dictionary
from transformers import AutoTokenizer, AutoModelForSeq2SeqLM, pipeline
import torch

model_name = "Helsinki-NLP/opus-mt-en-hi"  # example: English → Hindi
device = 0 if torch.cuda.is_available() else -1
translator = pipeline("translation", model=model_name, tokenizer=model_name, device=device)



def expand_abbreviations(text):
    def replacer(match):
        word = match.group(0)
        key = re.sub(r'\W+', '', word.lower())  # normalize for lookup
        punct = ''.join(re.findall(r'\W+', word))  # preserve punctuation

        # Check dictionary first
        if key in abbreviations:
            return abbreviations[key] + punct

        # Try regex pattern matches
        for pattern, replacement in pattern_expansions.items():
            if re.fullmatch(pattern, key):
                return replacement + punct

        # Default: return original
        return word

    return re.sub(r'\b\w+\W*', replacer, text)

from transformers import AutoTokenizer, AutoModelForSeq2SeqLM, pipeline

# Load AI correction model
model_name = "oliverguhr/spelling-correction-english-base"
tokenizer = AutoTokenizer.from_pretrained(model_name)
model = AutoModelForSeq2SeqLM.from_pretrained(model_name)
corrector = pipeline("text2text-generation", model=model, tokenizer=tokenizer)

def correct_text(text):
    result = corrector(text, max_length=256, clean_up_tokenization_spaces=True)
    return result[0]['generated_text']



@app.route('/send', methods=["POST"])
def send_message():
    """Handle message sending"""
    try:
        data = request.get_json()
        if not data:
            logger.warning("No data received in send request")
            return jsonify({"status": "error", "message": "No data provided"}), 400
        
        sender = data.get("from", "Anonymous")
        raw_text = data.get("text", "").strip()
        expanded_text = expand_abbreviations(raw_text)
        corrected_text = correct_text(expanded_text)  # this uses your AI model
        text = corrected_text        
        if not text:
            logger.warning("Empty message received")
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

@app.route('/messages')
def get_messages():
    """Retrieve and translate messages"""
    try:
        user_lang = request.args.get('lang', 'en')
        current_user = request.args.get('user', 'Anonymous')
        translated_messages = []
        
        logger.debug(f"Fetching messages for {current_user} (lang: {user_lang})")
        
        for msg in messages[-100:]:  # Limit to last 100 messages
            original = msg.get("original", "")
            sender = msg.get("from", "Unknown")
            
            # Don't translate user's own messages
            if sender == current_user:
                translated = original
            else:
                try:
                    translated = GoogleTranslator(
                        source='auto',
                        target=user_lang
                    ).translate(original[:5000])
                except Exception as e:
                    logger.error(f"Translation failed: {str(e)}")
                    translated = original

            
            translated_messages.append({
                "from": sender,
                "content": translated,  # Frontend only needs translated version
                "timestamp": msg.get("timestamp")
            })
        
        logger.debug(f"Returning {len(translated_messages)} messages")
        return jsonify({"messages": translated_messages})
    
    except Exception as e:
        logger.error(f"Error in get_messages: {str(e)}")
        return jsonify({"status": "error", "message": str(e)}), 500
    
    # Assuming you store messages in a global list like messages = []
@app.route("/clear", methods=["POST"])
def clear_messages():
    global messages
    messages = []
    print("Messages after clear:", messages)  # DEBUG
    return jsonify({"status": "cleared"})



if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5001)