from flask import Flask
from threading import Thread

app = Flask(__name__)

@app.route('/')
def home():
    return "✅ Bot Prakom Kejaksaan RI is running and healthy 24/7!"

def run():
    # Menjalankan web server pada port 8080 (standar Replit Webview)
    app.run(host='0.0.0.0', port=8080)

def keep_alive():
    t = Thread(target=run)
    t.daemon = True
    t.start()
