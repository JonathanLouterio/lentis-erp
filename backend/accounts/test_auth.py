from django.contrib.auth import get_user_model
from django.test import Client, TestCase


User = get_user_model()


class SessionAuthTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        # Credencial fictícia, usada somente no banco de testes.
        cls.password = "SenhaDeTeste!2026"
        cls.user = User.objects.create_user(
            username="usuario_auth",
            password=cls.password,
        )

    def setUp(self):
        # Exige CSRF de verdade, inclusive nas requisições de teste.
        self.client = Client(enforce_csrf_checks=True)

    def get_csrf_token(self):
        response = self.client.get("/api/auth/csrf/")
        self.assertEqual(response.status_code, 200)
        self.assertIn("csrftoken", self.client.cookies)
        return response.json()["csrfToken"]

    def login(self, token, password=None):
        return self.client.post(
            "/api/auth/login/",
            {
                "username": self.user.username,
                "password": self.password if password is None else password,
            },
            content_type="application/json",
            HTTP_X_CSRFTOKEN=token,
        )

    def test_login_me_and_logout(self):
        token = self.get_csrf_token()
        response = self.login(token)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json()["user"]["username"],
            self.user.username,
        )
        new_token = response.json()["csrfToken"]

        response = self.client.get("/api/me/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json(),
            {
                "id": self.user.pk,
                "username": self.user.username,
                "first_name": "",
                "last_name": "",
            },
        )

        # O token anterior ao login deve ter sido invalidado.
        response = self.client.post(
            "/api/auth/logout/",
            HTTP_X_CSRFTOKEN=token,
        )
        self.assertEqual(response.status_code, 403)

        # O token retornado pelo login deve permitir sair.
        response = self.client.post(
            "/api/auth/logout/",
            HTTP_X_CSRFTOKEN=new_token,
        )
        self.assertEqual(response.status_code, 200)

        self.assertEqual(
            self.client.get("/api/me/").status_code,
            403,
        )
        self.assertEqual(
            self.client.get("/api/me/stores/").status_code,
            403,
        )

    def test_login_without_csrf_is_denied(self):
        self.get_csrf_token()

        response = self.client.post(
            "/api/auth/login/",
            {
                "username": self.user.username,
                "password": self.password,
            },
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 403)
        self.assertEqual(
            self.client.get("/api/me/").status_code,
            403,
        )

    def test_logout_without_csrf_preserves_session(self):
        response = self.login(self.get_csrf_token())
        self.assertEqual(response.status_code, 200)

        response = self.client.post("/api/auth/logout/")

        self.assertEqual(response.status_code, 403)
        self.assertEqual(
            self.client.get("/api/me/").status_code,
            200,
        )

    def test_wrong_password_is_denied(self):
        response = self.login(
            self.get_csrf_token(),
            password="SenhaIncorreta!",
        )

        self.assertEqual(response.status_code, 401)
        self.assertEqual(
            response.json()["detail"],
            "Usuário ou senha inválidos.",
        )
        self.assertEqual(
            self.client.get("/api/me/").status_code,
            403,
        )

    def test_inactive_user_is_denied(self):
        self.user.is_active = False
        self.user.save()

        response = self.login(self.get_csrf_token())

        self.assertEqual(response.status_code, 401)
        self.assertEqual(
            response.json()["detail"],
            "Usuário ou senha inválidos.",
        )
        self.assertEqual(
            self.client.get("/api/me/").status_code,
            403,
        )

    def test_me_requires_login(self):
        response = self.client.get("/api/me/")
        self.assertEqual(response.status_code, 403)

    def test_login_and_logout_reject_get(self):
        for url in ("/api/auth/login/", "/api/auth/logout/"):
            with self.subTest(url=url):
                response = self.client.get(url)
                self.assertEqual(response.status_code, 405)