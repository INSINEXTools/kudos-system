"""HTTP Server and REST API for the Internal Kudos System."""

import json
import logging
import os
import re
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

import database

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

STATIC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")
DB_PATH = os.environ.get("KUDOS_DB_PATH", "kudos.db")


class KudosRequestHandler(BaseHTTPRequestHandler):
    """Handles static frontend assets and JSON REST API requests."""

    db_path = DB_PATH

    def _send_json(self, status_code: int, payload: dict) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _read_json_body(self):
        content_length = int(self.headers.get("Content-Length", 0))
        if content_length == 0:
            return {}
        raw = self.rfile.read(content_length)
        return json.loads(raw.decode("utf-8"))

    def _get_current_user(self):
        user_id_header = self.headers.get("X-User-Id")
        if not user_id_header:
            return None
        try:
            user_id = int(user_id_header)
        except ValueError:
            return None
        return database.get_user_by_id(user_id, db_path=self.db_path)

    def _serve_static(self, rel_path: str) -> None:
        safe_path = os.path.normpath(rel_path).lstrip(os.sep)
        full_path = os.path.join(STATIC_DIR, safe_path)
        if not os.path.abspath(full_path).startswith(os.path.abspath(STATIC_DIR)):
            self._send_json(403, {"error": "Forbidden"})
            return
        if not os.path.isfile(full_path):
            self._send_json(404, {"error": "File not found"})
            return

        content_types = {
            ".html": "text/html; charset=utf-8",
            ".css": "text/css; charset=utf-8",
            ".js": "application/javascript; charset=utf-8",
        }
        ext = os.path.splitext(full_path)[1].lower()
        content_type = content_types.get(ext, "application/octet-stream")

        with open(full_path, "rb") as f:
            content = f.read()

        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(content)))
        self.end_headers()
        self.wfile.write(content)

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path

        if path == "/" or path == "/index.html":
            self._serve_static("index.html")
            return
        if path.startswith("/static/"):
            self._serve_static(path[len("/static/"):])
            return

        if path == "/api/users":
            users = database.list_users(db_path=self.db_path)
            self._send_json(200, {"users": users})
            return

        if path == "/api/kudos":
            qs = parse_qs(parsed.query)
            try:
                page = int(qs.get("page", ["1"])[0])
                per_page = int(qs.get("per_page", ["10"])[0])
            except ValueError:
                self._send_json(400, {"error": "Invalid pagination parameters."})
                return

            include_hidden_req = qs.get("include_hidden", ["false"])[0].lower() == "true"
            user = self._get_current_user()
            include_hidden = include_hidden_req and user is not None and user["role"] == "admin"

            result = database.list_kudos(
                include_hidden=include_hidden,
                page=page,
                per_page=per_page,
                db_path=self.db_path,
            )
            self._send_json(200, result)
            return

        self._send_json(404, {"error": "Endpoint not found"})

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path != "/api/kudos":
            self._send_json(404, {"error": "Endpoint not found"})
            return

        user = self._get_current_user()
        if not user:
            self._send_json(401, {"error": "Authentication required (X-User-Id header)."})
            return

        try:
            body = self._read_json_body()
            recipient_id = int(body.get("recipient_id"))
            message = body.get("message", "")
        except (ValueError, TypeError, json.JSONDecodeError):
            self._send_json(400, {"error": "Invalid JSON payload or recipient_id."})
            return

        kudos, err = database.create_kudos(
            sender_id=user["id"],
            recipient_id=recipient_id,
            message=message,
            db_path=self.db_path,
        )
        if err:
            self._send_json(400, {"error": err})
            return

        logger.info("Kudos #%s created by user #%s for user #%s", kudos["id"], user["id"], recipient_id)
        self._send_json(201, {"kudos": kudos})

    def do_PATCH(self) -> None:
        parsed = urlparse(self.path)
        match = re.match(r"^/api/kudos/(\d+)/moderate$", parsed.path)
        if not match:
            self._send_json(404, {"error": "Endpoint not found"})
            return

        user = self._get_current_user()
        if not user:
            self._send_json(401, {"error": "Authentication required."})
            return

        kudos_id = int(match.group(1))
        try:
            body = self._read_json_body()
            if "is_visible" not in body or not isinstance(body["is_visible"], bool):
                self._send_json(400, {"error": "'is_visible' boolean field is required."})
                return
            is_visible = body["is_visible"]
            reason = body.get("reason_for_moderation", "")
        except json.JSONDecodeError:
            self._send_json(400, {"error": "Invalid JSON payload."})
            return

        updated, err = database.moderate_kudos(
            kudos_id=kudos_id,
            admin_id=user["id"],
            is_visible=is_visible,
            reason=reason,
            db_path=self.db_path,
        )
        if err:
            status = 403 if "Forbidden" in err else (404 if "not found" in err else 400)
            self._send_json(status, {"error": err})
            return

        logger.info("Kudos #%s moderated by admin #%s (is_visible=%s)", kudos_id, user["id"], is_visible)
        self._send_json(200, {"kudos": updated})

    def do_DELETE(self) -> None:
        parsed = urlparse(self.path)
        match = re.match(r"^/api/kudos/(\d+)$", parsed.path)
        if not match:
            self._send_json(404, {"error": "Endpoint not found"})
            return

        user = self._get_current_user()
        if not user:
            self._send_json(401, {"error": "Authentication required."})
            return

        kudos_id = int(match.group(1))
        deleted, err = database.delete_kudos(
            kudos_id=kudos_id,
            admin_id=user["id"],
            db_path=self.db_path,
        )
        if err:
            status = 403 if "Forbidden" in err else 404
            self._send_json(status, {"error": err})
            return

        logger.info("Kudos #%s permanently deleted by admin #%s", kudos_id, user["id"])
        self._send_json(200, {"deleted": True, "id": kudos_id})


def run_server(host: str = "127.0.0.1", port: int = 8000, db_path: str = DB_PATH) -> None:
    """Initialize DB and start the threaded HTTP server."""
    database.init_db(db_path=db_path, seed=True)
    KudosRequestHandler.db_path = db_path
    server = ThreadingHTTPServer((host, port), KudosRequestHandler)
    logger.info("Kudos System running at http://%s:%s", host, port)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        logger.info("Shutting down server...")
        server.server_close()


if __name__ == "__main__":
    run_server()
