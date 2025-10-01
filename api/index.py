from flask import Flask, jsonify, request
from flask_cors import CORS
from mangum import Mangum  # optional: serverless adapter

app = Flask(__name__)
CORS(app)

@app.route("/")
def home():
    return jsonify({"message": "Hello from Flask on Vercel!"})

# Required for Vercel serverless function
def handler(event, context):
    from werkzeug.middleware.proxy_fix import ProxyFix
    app.wsgi_app = ProxyFix(app.wsgi_app)
    from werkzeug.wrappers import Request, Response

    request = Request(event)
    response = app.full_dispatch_request()
    return Response(response)
