from pathlib import Path
import argparse
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
        data = request.get_json(silent=True) or {}
        text = str(data.get("message", "")).strip()
        if not text:
            return jsonify({"error": "message required"}), 400
        return jsonify({"reply": client.chat(text)})

    @app.get("/api/knowledge")
    def list_knowledge():
        return jsonify({"items": knowledge.all()})

    @app.delete("/api/knowledge/<item_id>")
    def delete_knowledge(item_id):
        return jsonify({"deleted": knowledge.delete(item_id)})

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
