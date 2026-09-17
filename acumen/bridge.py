from pathlib import Path
import argparse
import secrets
from threading import RLock
from flask import Flask, request, jsonify, send_from_directory
from .config import load_config
from .client import AcumenClient
from .knowledge import KnowledgeStore

def make_app(root: Path, cfg):
    app = Flask(__name__, static_folder=None)
    frontend = Path(__file__).resolve().parents[1] / "docs"
    client = AcumenClient("local", root, cfg)
    knowledge = KnowledgeStore(root)
    token = cfg["web"].get("pairing_token")
    if not isinstance(token, str) or not token.strip() or token == "change-me":
        token = secrets.token_urlsafe(32)
    allowed = set(cfg["web"].get("allowed_origins", []))
    lock = RLock()
    app.extensions["acumen_client"] = client
    app.config["ACUMEN_PAIRING_TOKEN"] = token

    @app.after_request
    def cors(resp):
        origin = request.headers.get("Origin")
        if origin in allowed:
            resp.headers["Access-Control-Allow-Origin"] = origin
            resp.headers["Access-Control-Allow-Headers"] = "Content-Type, X-Acumen-Token"
            resp.headers["Access-Control-Allow-Methods"] = "GET, POST, DELETE, OPTIONS"
        return resp

    @app.before_request
    def auth():
        if request.method == "OPTIONS":
            return ("", 204)
        if request.path in {"/", "/index.html", "/app.js", "/style.css", "/health"} and request.method in {"GET", "HEAD"}:
            return None
        if request.headers.get("X-Acumen-Token") != token:
            return jsonify({"error": "bad pairing token"}), 401

    @app.get("/")
    @app.get("/index.html")
    def index():
        return send_from_directory(frontend, "index.html")

    @app.get("/app.js")
    def javascript():
        return send_from_directory(frontend, "app.js")

    @app.get("/style.css")
    def stylesheet():
        return send_from_directory(frontend, "style.css")

    @app.get("/health")
    def health():
        return {"ok": True, "name": "AcumenAI local bridge"}

    @app.post("/api/chat")
    def chat():
        data = request.get_json(silent=True)
        if not isinstance(data, dict) or not isinstance(data.get("message"), str):
            return jsonify({"error": "message must be text"}), 400
        text = data["message"].strip()
        if not text:
            return jsonify({"error": "message required"}), 400
        with lock:
            return jsonify({"reply": client.chat(text)})

    @app.get("/api/session")
    def session_status():
        with lock:
            data = client.session_store.get(client.session_id) or {}
            return jsonify({"candidates": data.get("candidates", []), "show_sources": client.show_sources})

    @app.post("/api/session/learning")
    def resolve_learning():
        data = request.get_json(silent=True)
        if not isinstance(data, dict) or not isinstance(data.get("action"), str) or data["action"] not in {"save", "discard"}:
            return jsonify({"error": "Choose save or discard."}), 400
        with lock:
            return jsonify(client._execute("session_learning", data["action"]))

    @app.get("/api/knowledge")
    def list_knowledge():
        with lock:
            return jsonify({"items": knowledge.all()})

    @app.delete("/api/knowledge/<item_id>")
    def delete_knowledge(item_id):
        with lock:
            deleted = knowledge.delete(item_id)
            return jsonify({"deleted": deleted}), 200 if deleted else 404

    return app

def main():
    ap = argparse.ArgumentParser(description="Run the AcumenAI localhost website and API together.")
    ap.add_argument("--root", default=None, help="Knowledge directory (default: storage.root in config, or data)")
    ap.add_argument("--config", default="config.yaml")
    ap.add_argument("--port", type=int, default=None)
    args = ap.parse_args()

    cfg = load_config(args.config)
    root = Path(args.root or cfg["storage"]["root"]).expanduser().resolve()
    host = cfg["web"]["bridge_host"]
    port = args.port if args.port is not None else int(cfg["web"]["bridge_port"])
    if not 1 <= port <= 65535:
        ap.error("port must be between 1 and 65535")
    app = make_app(root, cfg)
    print(f"Acumen website: http://{host}:{port}", flush=True)
    print(f"Pairing token: {app.config['ACUMEN_PAIRING_TOKEN']}", flush=True)
    print("Open the website, click Pair, and paste the token above.", flush=True)
    print("Use New learning > Save all before stopping. Press Ctrl+C to stop.", flush=True)
    try:
        app.run(host=host, port=port, debug=False)
    finally:
        app.extensions["acumen_client"].local_processor.close()
