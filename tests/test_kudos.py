"""Unit and integration tests for the Kudos System."""

import json
import os
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer

import app
import database


class TestKudosSystem(unittest.TestCase):
    """End-to-end API and database tests covering submission, validation, and moderation."""

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.temp_dir.name, "test_kudos.db")
        database.init_db(db_path=self.db_path, seed=True)

        class TestHandler(app.KudosRequestHandler):
            db_path = self.db_path
            def log_message(self, format, *args):
                pass  # Silence request logs during tests

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), TestHandler)
        self.port = self.server.server_address[1]
        self.base_url = f"http://127.0.0.1:{self.port}"
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.temp_dir.cleanup()

    def _request(self, method, path, body=None, user_id=None):
        data = json.dumps(body).encode("utf-8") if body is not None else None
        headers = {"Content-Type": "application/json"}
        if user_id is not None:
            headers["X-User-Id"] = str(user_id)
        req = urllib.request.Request(
            f"{self.base_url}{path}", data=data, headers=headers, method=method
        )
        try:
            with urllib.request.urlopen(req) as resp:
                return resp.status, json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read().decode("utf-8"))

    def test_list_users_and_public_feed(self):
        status, users_data = self._request("GET", "/api/users")
        self.assertEqual(status, 200)
        self.assertEqual(len(users_data["users"]), 5)

        status, feed_data = self._request("GET", "/api/kudos")
        self.assertEqual(status, 200)
        self.assertEqual(feed_data["total"], 2)

    def test_create_kudos_and_validation(self):
        # Valid kudos from user 1 to user 3
        status, data = self._request(
            "POST",
            "/api/kudos",
            body={"recipient_id": 3, "message": "Awesome sprint demo!"},
            user_id=1,
        )
        self.assertEqual(status, 201)
        self.assertEqual(data["kudos"]["recipient_id"], 3)

        # Duplicate kudos within window should be rejected
        status, err = self._request(
            "POST",
            "/api/kudos",
            body={"recipient_id": 3, "message": "Awesome sprint demo!"},
            user_id=1,
        )
        self.assertEqual(status, 400)
        self.assertIn("Duplicate", err["error"])

        # Self-kudos rejected
        status, err = self._request(
            "POST",
            "/api/kudos",
            body={"recipient_id": 1, "message": "I am great"},
            user_id=1,
        )
        self.assertEqual(status, 400)

        # Over 500 characters rejected
        status, err = self._request(
            "POST",
            "/api/kudos",
            body={"recipient_id": 2, "message": "a" * 501},
            user_id=1,
        )
        self.assertEqual(status, 400)

    def test_moderation_hide_restore_and_permissions(self):
        # Regular employee (id=1) cannot moderate
        status, err = self._request(
            "PATCH",
            "/api/kudos/1/moderate",
            body={"is_visible": False, "reason_for_moderation": "Test"},
            user_id=1,
        )
        self.assertEqual(status, 403)

        # Admin (id=5) hides kudos #1
        status, data = self._request(
            "PATCH",
            "/api/kudos/1/moderate",
            body={"is_visible": False, "reason_for_moderation": "Inappropriate content"},
            user_id=5,
        )
        self.assertEqual(status, 200)
        self.assertEqual(data["kudos"]["is_visible"], 0)
        self.assertEqual(data["kudos"]["moderated_by"], 5)
        self.assertEqual(data["kudos"]["reason_for_moderation"], "Inappropriate content")

        # Public feed now only shows 1 visible kudos
        status, public_feed = self._request("GET", "/api/kudos", user_id=1)
        self.assertEqual(public_feed["total"], 1)

        # Admin requesting include_hidden=true sees both
        status, admin_feed = self._request(
            "GET", "/api/kudos?include_hidden=true", user_id=5
        )
        self.assertEqual(admin_feed["total"], 2)

        # Admin restores kudos #1
        status, restored = self._request(
            "PATCH",
            "/api/kudos/1/moderate",
            body={"is_visible": True},
            user_id=5,
        )
        self.assertEqual(status, 200)
        self.assertEqual(restored["kudos"]["is_visible"], 1)

    def test_admin_delete_kudos(self):
        # Regular employee cannot delete
        status, _ = self._request("DELETE", "/api/kudos/2", user_id=1)
        self.assertEqual(status, 403)

        # Admin can permanently delete
        status, data = self._request("DELETE", "/api/kudos/2", user_id=5)
        self.assertEqual(status, 200)
        self.assertTrue(data["deleted"])

        status, feed = self._request("GET", "/api/kudos")
        self.assertEqual(feed["total"], 1)


if __name__ == "__main__":
    unittest.main()
