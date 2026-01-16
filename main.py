import os
from flask import Flask, render_template
import subprocess
import threading

app = Flask(__name__)

def run_discord_bot():
    subprocess.call(["python3", "ds.py"])

@app.route("/")
def index():
    return render_template("index.html")

if __name__ == "__main__":
    # Avvia il bot Discord in un thread separato
    threading.Thread(target=run_discord_bot, daemon=True).start()
    # Ottieni la porta dal sistema o usa 10000 come default
    port = int(os.environ.get("PORT", 10000))
    # Avvia il server Flask
    app.run(host="0.0.0.0", port=port)

