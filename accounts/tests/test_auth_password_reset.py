from __future__ import annotations

from django.contrib.auth import get_user_model
from django.core import mail
from django.test import TestCase
from django.utils.http import urlsafe_base64_encode
from django.utils.encoding import force_bytes
from django.contrib.auth.tokens import default_token_generator

User = get_user_model()


class PasswordResetFlowTests(TestCase):
    def setUp(self) -> None:
        self.reset_url = "/api/auth/password/reset/"
        self.confirm_url = "/api/auth/password/reset/confirm/"
        self.csrf_url = "/api/auth/csrf/"

    def _csrf_headers(self):
        # Prime CSRF cookie and return appropriate header for POSTs
        resp = self.client.get(self.csrf_url)
        self.assertEqual(resp.status_code, 204)
        csrftoken = self.client.cookies.get("csrftoken").value
        return {"HTTP_X_CSRFTOKEN": csrftoken}

    def test_request_returns_204_and_sends_email_for_existing_user(self):
        User.objects.create_user(username="alice", email="alice@example.com", password="xYz!23456")
        mail.outbox.clear()

        headers = self._csrf_headers()
        resp = self.client.post(self.reset_url, {"email": "alice@example.com"}, content_type="application/json", **headers)
        self.assertEqual(resp.status_code, 204)
        self.assertEqual(len(mail.outbox), 1)
        body = mail.outbox[0].body
        # Dev-friendly body contains UID and TOKEN lines
        self.assertIn("UID:", body)
        self.assertIn("TOKEN:", body)

    def test_request_returns_204_and_sends_no_email_for_unknown(self):
        mail.outbox.clear()
        headers = self._csrf_headers()
        resp = self.client.post(self.reset_url, {"email": "nobody@example.com"}, content_type="application/json", **headers)
        self.assertEqual(resp.status_code, 204)
        self.assertEqual(len(mail.outbox), 0)

    def test_request_requires_csrf(self):
        resp = self.client.post(self.reset_url, {"email": "x@example.com"}, content_type="application/json")
        self.assertEqual(resp.status_code, 403)

    def test_confirm_invalid_token_400(self):
        # Create a user and send an obviously invalid token
        u = User.objects.create_user(username="bob", email="bob@example.com", password="xYz!23456")
        uid = urlsafe_base64_encode(force_bytes(u.pk))
        headers = self._csrf_headers()
        payload = {"uid": uid, "token": "invalid-token", "new_password1": "N3wPass!234", "new_password2": "N3wPass!234"}
        resp = self.client.post(self.confirm_url, payload, content_type="application/json", **headers)
        self.assertEqual(resp.status_code, 400)

    def test_confirm_success_sets_password_and_allows_login(self):
        u = User.objects.create_user(username="carol", email="carol@example.com", password="Old!Pass123")
        uid = urlsafe_base64_encode(force_bytes(u.pk))
        token = default_token_generator.make_token(u)

        headers = self._csrf_headers()
        payload = {"uid": uid, "token": token, "new_password1": "BrandNew!234", "new_password2": "BrandNew!234"}
        resp = self.client.post(self.confirm_url, payload, content_type="application/json", **headers)
        self.assertEqual(resp.status_code, 204)

        # Old password should no longer work
        self.assertFalse(self.client.login(username="carol", password="Old!Pass123"))
        # New password works
        self.assertTrue(self.client.login(username="carol", password="BrandNew!234"))

    def test_confirm_requires_csrf(self):
        u = User.objects.create_user(username="dave", email="dave@example.com", password="Old!Pass123")
        uid = urlsafe_base64_encode(force_bytes(u.pk))
        token = default_token_generator.make_token(u)
        resp = self.client.post(
            self.confirm_url,
            {"uid": uid, "token": token, "new_password1": "BrandNew!234", "new_password2": "BrandNew!234"},
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 403)

    def test_request_throttled(self):
        User.objects.create_user(username="eve", email="eve@example.com", password="xYz!23456")
        headers = self._csrf_headers()
        # default rate: 5/min
        for i in range(5):
            r = self.client.post(self.reset_url, {"email": "eve@example.com"}, content_type="application/json", **headers)
            self.assertEqual(r.status_code, 204)
        r6 = self.client.post(self.reset_url, {"email": "eve@example.com"}, content_type="application/json", **headers)
        self.assertEqual(r6.status_code, 429)
