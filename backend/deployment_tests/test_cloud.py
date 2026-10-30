import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from unittest.mock import patch

from django.db import OperationalError
from django.test import RequestFactory, SimpleTestCase, override_settings

from config.deployment_views import NoIndexMiddleware, frontend, health


class DeploymentTests(SimpleTestCase):
    def settings_process(self, hosts="homolog.example", key=None):
        env = {**os.environ, "DJANGO_ALLOWED_HOSTS": hosts, "RENDER_EXTERNAL_HOSTNAME": "",
               "DJANGO_SECRET_KEY": key or "test-only-0123456789-abcdefghijklmnopqrstuvwxyz-ABCDEFGHIJKLMNOPQRSTUVWXYZ"}
        return subprocess.run([sys.executable, "-c",
            "import json; from config import settings_production as s; "
            "print(json.dumps({'debug':s.DEBUG, 'hosts':s.ALLOWED_HOSTS, "
            "'origins':s.CSRF_TRUSTED_ORIGINS, 'secure':s.SESSION_COOKIE_SECURE, "
            "'csrf_secure':s.CSRF_COOKIE_SECURE, 'redirect':s.SECURE_SSL_REDIRECT}))"],
            env=env, capture_output=True, text=True, cwd=Path(__file__).resolve().parents[1])

    def test_production_enforces_https_and_exact_host(self):
        result = self.settings_process()
        self.assertEqual(result.returncode, 0, result.stderr)
        data = json.loads(result.stdout)
        self.assertFalse(data["debug"])
        self.assertEqual(data["hosts"], ["homolog.example"])
        self.assertEqual(data["origins"], ["https://homolog.example"])
        self.assertTrue(data["secure"] and data["csrf_secure"] and data["redirect"])

    def test_production_rejects_missing_wildcard_and_url_host(self):
        for host in ("", "*", ".example.com", "https://example.com"):
            with self.subTest(host=host):
                self.assertNotEqual(self.settings_process(hosts=host).returncode, 0)

    def test_production_rejects_weak_secret(self):
        self.assertNotEqual(self.settings_process(key="short-key").returncode, 0)

    def test_frontend_html_is_not_cached(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / "index.html").write_text("<!doctype html><title>Lentis</title>", encoding="utf-8")
            with override_settings(FRONTEND_DIST=root):
                response = frontend(RequestFactory().get("/"))
                self.assertEqual(response.status_code, 200)
                self.assertIn("no-store", response["Cache-Control"])
                self.assertIn(b"Lentis", b"".join(response.streaming_content))
                response.close()

    def test_missing_frontend_returns_service_unavailable(self):
        with tempfile.TemporaryDirectory() as folder, override_settings(FRONTEND_DIST=Path(folder)):
            self.assertEqual(frontend(RequestFactory().get("/")).status_code, 503)

    def test_frontend_rejects_post(self):
        self.assertEqual(frontend(RequestFactory().post("/")).status_code, 405)

    def test_health_checks_database(self):
        with patch("config.deployment_views.connection") as database:
            cursor = database.cursor
            result = health(RequestFactory().get("/healthz/"))
            self.assertEqual(result.status_code, 200)
            cursor.return_value.__enter__.return_value.execute.assert_called_once_with("SELECT 1")
            self.assertIn("no-store", result["Cache-Control"])

    def test_health_failure_does_not_expose_database_details(self):
        with patch("config.deployment_views.connection") as database:
            database.cursor.side_effect = OperationalError("private-host secret")
            result = health(RequestFactory().get("/healthz/"))
            self.assertEqual(result.status_code, 503)
            self.assertNotIn(b"private-host", result.content)

    def test_homologation_responses_discourage_indexing(self):
        from django.http import HttpResponse
        response = NoIndexMiddleware(lambda request: HttpResponse("ok"))(RequestFactory().get("/"))
        self.assertEqual(response["X-Robots-Tag"], "noindex, nofollow, noarchive")
