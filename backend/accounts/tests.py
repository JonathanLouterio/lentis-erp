from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from django.test import TestCase

from organizations.models import Company, Store

from .models import StoreMembership
from .selectors import get_accessible_stores


User = get_user_model()


class AccessibleStoresTests(TestCase):
    def setUp(self):
        self.company = Company.objects.create(name="Empresa Teste")
        self.store = Store.objects.create(
            company=self.company, code="001", name="Matriz"
        )
        self.other_store = Store.objects.create(
            company=self.company, code="002", name="Filial"
        )
        self.user = User.objects.create_user(username="vendedor")
        self.membership = StoreMembership.objects.create(
            user=self.user,
            store=self.store,
            role=StoreMembership.Role.SELLER,
        )

        # Outro usuário ativo na matriz não deve liberar nosso vendedor.
        other_user = User.objects.create_user(username="outro")
        StoreMembership.objects.create(
            user=other_user,
            store=self.store,
            role=StoreMembership.Role.SELLER,
        )

    def test_returns_only_linked_store(self):
        self.assertQuerySetEqual(
            get_accessible_stores(self.user),
            [self.store],
        )

    def test_anonymous_has_no_stores(self):
        self.assertFalse(
            get_accessible_stores(AnonymousUser()).exists()
        )

    def test_user_without_membership_has_no_stores(self):
        user = User.objects.create_user(username="sem_vinculo")
        self.assertFalse(get_accessible_stores(user).exists())

    def test_staff_does_not_bypass_membership(self):
        self.user.is_staff = True
        self.user.save()
        self.assertQuerySetEqual(
            get_accessible_stores(self.user),
            [self.store],
        )

    def test_inactive_entities_block_access(self):
        for obj in (
            self.user,
            self.membership,
            self.store,
            self.company,
        ):
            with self.subTest(model=obj.__class__.__name__):
                obj.is_active = False
                obj.save()
                self.assertFalse(
                    get_accessible_stores(self.user).exists()
                )
                obj.is_active = True
                obj.save()

    def test_superuser_sees_active_stores_without_membership(self):
        admin = User.objects.create_superuser(username="admin_teste")
        self.assertQuerySetEqual(
            get_accessible_stores(admin),
            [self.store, self.other_store],
        )

        self.other_store.is_active = False
        self.other_store.save()
        self.assertQuerySetEqual(
            get_accessible_stores(admin),
            [self.store],
        )

        self.company.is_active = False
        self.company.save()
        self.assertFalse(get_accessible_stores(admin).exists())

    def test_inactive_superuser_has_no_stores(self):
        admin = User.objects.create_superuser(
            username="admin_inativo",
            is_active=False,
        )
        self.assertFalse(get_accessible_stores(admin).exists())

class MyStoresAPITests(TestCase):
    def setUp(self):
        self.url = "/api/me/stores/"
        self.company = Company.objects.create(name="Empresa API")

        self.store = Store.objects.create(
            company=self.company, code="001", name="Matriz"
        )
        self.other_store = Store.objects.create(
            company=self.company, code="002", name="Filial"
        )

        self.user = User.objects.create_user(username="vendedor_api")

        self.membership = StoreMembership.objects.create(
            user=self.user,
            store=self.store,
            role=StoreMembership.Role.SELLER,
        )

    def test_anonymous_request_is_denied(self):
        response = self.client.get(
            self.url, HTTP_ACCEPT="application/json"
        )
        self.assertEqual(response.status_code, 403)

    def test_returns_only_authorized_store(self):
        self.client.force_login(self.user)

        response = self.client.get(
            self.url, HTTP_ACCEPT="application/json"
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json(),
            [
                {
                    "id": self.store.pk,
                    "code": "001",
                    "name": "Matriz",
                    "role": "seller",
                    "role_label": "Vendedor",
                }
            ],
        )

    def test_revocation_applies_to_existing_session(self):
        self.client.force_login(self.user)

        response = self.client.get(
            self.url, HTTP_ACCEPT="application/json"
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.json()), 1)

        self.membership.is_active = False
        self.membership.save()

        # Repete a consulta na mesma sessão, sem novo login.
        response = self.client.get(
            self.url, HTTP_ACCEPT="application/json"
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), [])

    def test_roles_are_specific_to_user_and_store(self):
        StoreMembership.objects.create(
            user=self.user,
            store=self.other_store,
            role=StoreMembership.Role.MANAGER,
        )
        other_user = User.objects.create_user(username="outro_perfil")
        StoreMembership.objects.create(
            user=other_user,
            store=self.store,
            role=StoreMembership.Role.FINANCE,
        )
        self.client.force_login(self.user)
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            [(item["id"], item["role"], item["role_label"])
             for item in response.json()],
            [
                (self.store.pk, "seller", "Vendedor"),
                (self.other_store.pk, "manager", "Gerente"),
            ],
        )

    def test_role_change_applies_to_existing_session(self):
        self.client.force_login(self.user)
        self.assertEqual(self.client.get(self.url).json()[0]["role"], "seller")

        self.membership.role = StoreMembership.Role.CASHIER
        self.membership.save(update_fields=["role"])
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()[0]["role"], "cashier")
        self.assertEqual(response.json()[0]["role_label"], "Caixa")

    def test_superuser_role_with_and_without_membership(self):
        admin = User.objects.create_superuser(username="admin_perfil")
        StoreMembership.objects.create(
            user=admin,
            store=self.store,
            role=StoreMembership.Role.SELLER,
        )
        self.client.force_login(admin)
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            [(item["id"], item["role"], item["role_label"])
             for item in response.json()],
            [
                (self.store.pk, "superuser", "Administrador do sistema"),
                (self.other_store.pk, "superuser", "Administrador do sistema"),
            ],
        )
