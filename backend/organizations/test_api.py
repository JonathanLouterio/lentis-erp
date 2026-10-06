from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from accounts.models import StoreMembership

from .models import Company, Customer, Store


User = get_user_model()


class MyCustomersAPITests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.company = Company.objects.create(name="Empresa Clientes")
        self.store = Store.objects.create(
            company=self.company, code="001", name="Matriz"
        )
        self.other_store = Store.objects.create(
            company=self.company, code="002", name="Filial"
        )
        self.user = User.objects.create_user(username="cliente_api")
        StoreMembership.objects.create(
            user=self.user,
            store=self.store,
            role=StoreMembership.Role.SELLER,
        )
        Customer.objects.create(
            store=self.store, name="Cliente Matriz", cpf="11111111111"
        )
        Customer.objects.create(
            store=self.other_store, name="Cliente Filial", cpf="22222222222"
        )
        self.url = "/api/me/customers/"

    def test_anonymous_request_is_denied(self):
        response = self.client.get(
            self.url,
            {"store_id": self.store.pk},
            HTTP_ACCEPT="application/json",
        )
        self.assertEqual(response.status_code, 403)

    def test_lists_only_active_customers_from_authorized_store(self):
        self.client.force_authenticate(self.user)
        response = self.client.get(self.url, {"store_id": self.store.pk})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]["name"], "Cliente Matriz")
        self.assertEqual(response.data[0]["store"], self.store.pk)

    def test_other_store_is_rejected(self):
        self.client.force_authenticate(self.user)
        response = self.client.get(
            self.url, {"store_id": self.other_store.pk}
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("store_id", response.data)

    def test_missing_store_is_rejected(self):
        self.client.force_authenticate(self.user)
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 400)
        self.assertIn("store_id", response.data)

    def test_creates_customer_in_selected_store(self):
        self.client.force_authenticate(self.user)
        response = self.client.post(
            f"{self.url}?store_id={self.store.pk}",
            {
                "name": "Novo Cliente",
                "cpf": "529.982.247-25",
                "phone": "(41) 99999-0000",
            },
            format="json",
        )

        self.assertEqual(response.status_code, 201)
        customer = Customer.objects.get(name="Novo Cliente")
        self.assertEqual(customer.store_id, self.store.pk)
        self.assertEqual(customer.cpf, "52998224725")

    def test_cannot_create_customer_in_other_store(self):
        self.client.force_authenticate(self.user)
        response = self.client.post(
            f"{self.url}?store_id={self.other_store.pk}",
            {"name": "Cliente Bloqueado"},
            format="json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertFalse(
            Customer.objects.filter(name="Cliente Bloqueado").exists()
        )
