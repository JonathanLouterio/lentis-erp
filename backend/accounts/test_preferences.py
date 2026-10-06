import json

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse


User = get_user_model()


class UserPreferencesTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="tema.usuario",
            password="SenhaTeste123!",
        )
        self.other_user = User.objects.create_user(
            username="outro.usuario",
            password="OutraSenha123!",
        )
        self.client = Client(enforce_csrf_checks=True)
        self.url = reverse("accounts:my-preferences")

    def authenticate(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse("accounts:csrf"))
        return response.json()["csrfToken"]

    def patch_preferences(self, data, token=None):
        headers = {}
        if token:
            headers["HTTP_X_CSRFTOKEN"] = token

        return self.client.patch(
            self.url,
            data=json.dumps(data),
            content_type="application/json",
            **headers,
        )

    def test_anonymous_access_is_denied(self):
        self.assertEqual(self.client.get(self.url).status_code, 403)
        response = self.patch_preferences({"theme": "dark"})
        self.assertEqual(response.status_code, 403)

    def test_default_theme_is_system(self):
        self.authenticate()
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"theme": "system"})

    def test_valid_themes_persist_and_appear_in_me(self):
        token = self.authenticate()

        for theme in ("light", "dark", "system"):
            with self.subTest(theme=theme):
                response = self.patch_preferences(
                    {"theme": theme},
                    token,
                )

                self.assertEqual(response.status_code, 200)
                self.user.refresh_from_db()
                self.assertEqual(self.user.theme, theme)

                me = self.client.get(reverse("accounts:me"))
                self.assertEqual(me.json()["theme"], theme)

    def test_invalid_theme_does_not_change_preference(self):
        token = self.authenticate()

        for theme in ("purple", "", None):
            with self.subTest(theme=theme):
                response = self.patch_preferences(
                    {"theme": theme},
                    token,
                )

                self.assertEqual(response.status_code, 400)
                self.user.refresh_from_db()
                self.assertEqual(self.user.theme, "system")

    def test_patch_without_csrf_is_denied(self):
        self.authenticate()
        response = self.patch_preferences({"theme": "dark"})

        self.assertEqual(response.status_code, 403)
        self.user.refresh_from_db()
        self.assertEqual(self.user.theme, "system")

    def test_update_cannot_target_another_user_or_change_permissions(self):
        token = self.authenticate()
        response = self.patch_preferences(
            {
                "theme": "dark",
                "id": self.other_user.pk,
                "username": "alterado",
                "is_staff": True,
                "is_superuser": True,
            },
            token,
        )

        self.assertEqual(response.status_code, 200)

        self.user.refresh_from_db()
        self.other_user.refresh_from_db()

        self.assertEqual(self.user.theme, "dark")
        self.assertEqual(self.user.username, "tema.usuario")
        self.assertFalse(self.user.is_staff)
        self.assertFalse(self.user.is_superuser)
        self.assertEqual(self.other_user.theme, "system")
        self.assertEqual(self.other_user.username, "outro.usuario")