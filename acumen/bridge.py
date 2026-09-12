from pathlib import Path
import argparse
from threading import RLock
from flask import Flask, request, jsonify
from .config import load_config
from .client import AcumenClient
from .knowledge import KnowledgeStore

def make_app(root: Path, cfg):
    app = Flask(__name__)
    client = AcumenClient("local", root, cfg)
    knowledge = KnowledgeStore(root)
    token = cfg["web"]["pairing_token"]
    allowed = set(cfg["web"].get("allowed_origins", []))
    lock = RLock()
    app.extensions["acumen_client"] = client

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
        if request.path == "/health":
            return None
        if request.headers.get("X-Acumen-Token") != token:
            return jsonify({"error": "bad pairing token"}), 401

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
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default="data")
    ap.add_argument("--config", default="config.yaml")
    ap.add_argument("--port", type=int, default=None)
    args = ap.parse_args()

    cfg = load_config(args.config)
    root = Path(args.root).expanduser().resolve()
    app = make_app(root, cfg)
    host = cfg["web"]["bridge_host"]
    port = args.port or int(cfg["web"]["bridge_port"])
    print(f"Acumen bridge: http://{host}:{port}")
    app.run(host=host, port=port, debug=False)
