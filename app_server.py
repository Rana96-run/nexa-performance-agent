"""
app_server.py
=============
Minimal Flask entrypoint for Railway deployment.

Imports the app factory from reports/app.py and starts the server.
Railway auto-deploys from origin/main — no background threads, no subprocesses.

Usage (Railway / Procfile):
    web: python app_server.py

Usage (local):
    python app_server.py
"""
from reports.app import create_app
import os

app = create_app()

if __name__ == "__main__":
    port = int(os.getenv("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
