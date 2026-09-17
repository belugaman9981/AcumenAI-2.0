from pathlib import Path
from io import BytesIO
import argparse
import secrets
from threading import RLock
from flask import Flask, request, jsonify, send_from_directory
from werkzeug.exceptions import HTTPException, InternalServerError, RequestEntityTooLarge
from werkzeug.wsgi import get_input_stream
from .config import load_config
from .client import AcumenClient
from .knowledge import KnowledgeStore
from .sessions import candidate_review_id, PendingLearningChanged

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
    app.config["MAX_CONTENT_LENGTH"] = 64 * 1024

    @app.errorhandler(HTTPException)
    def http_error(error):
        if not request.path.startswith("/api/"):
            return error
        response = error.get_response()
        message = error.description
        if isinstance(error, RequestEntityTooLarge):
            message = "This request is too large. Shorten your message and try again (64 KiB limit)."
        response.data = app.json.dumps({"error": message})
        response.content_type = "application/json"
        return response

    @app.errorhandler(Exception)
    def unexpected_error(error):
        app.logger.exception("Unable to complete %s %s", request.method, request.path)
        if not request.path.startswith("/api/"):
            return InternalServerError()
        return jsonify({
            "error": "The local server could not complete this request. Check the server terminal for details."
        }), 500

    @app.after_request
    def cors(resp):
        if request.path.startswith("/api/"):
            resp.headers["Cache-Control"] = "no-store"
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
        limit = app.config["MAX_CONTENT_LENGTH"]
        if request.content_length is not None and request.content_length > limit:
            raise RequestEntityTooLarge()
        if request.environ.get("wsgi.input_terminated"):
            # Read one extra byte to distinguish a complete body at the limit
            # from a chunked body that Werkzeug would otherwise truncate.
            body = get_input_stream(request.environ, max_content_length=limit + 1).read()
            if len(body) > limit:
                raise RequestEntityTooLarge()
            request.environ["wsgi.input"] = BytesIO(body)

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
            candidates = [dict(candidate, review_id=candidate_review_id(candidate))
                          for candidate in data.get("candidates", [])]
            return jsonify({"candidates": candidates, "show_sources": client.show_sources})

    @app.post("/api/session/learning")
    def resolve_learning():
        data = request.get_json(silent=True)
        if not isinstance(data, dict) or not isinstance(data.get("action"), str) or data["action"] not in {"save", "discard"}:
            return jsonify({"error": "Choose save or discard."}), 400
        if "item_id" in data and (not isinstance(data["item_id"], str) or not data["item_id"].strip()):
            return jsonify({"error": "item_id must be nonempty text."}), 400
        with lock:
            if "item_id" in data:
                try:
                    count = client.session_store.resolve_pending(
                        client.session_id, data["action"], knowledge, item_id=data["item_id"],
                    )
                except PendingLearningChanged as error:
                    return jsonify({"error": str(error)}), 409
                verb = "Saved" if data["action"] == "save" else "Discarded"
                return jsonify({"ok": True, "answer": f"{verb} {count} learning item(s).", "count": count})
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
