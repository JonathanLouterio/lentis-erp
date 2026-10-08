from decimal import Decimal

from django.contrib import admin
from django.contrib.auth import get_user_model
from django.test import RequestFactory, TestCase
from rest_framework.test import APIClient

from .models import Company, Product, StockMovement, Store
from .serializers import ProductSerializer
from .stock_services import register_stock_movement


class StockMovementAPITests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_superuser(
            username="stock_api_admin", email="stock-api@example.com", password="test-only-password",
        )
        company = Company.objects.create(name="Empresa API")
        self.store = Store.objects.create(company=company, code="01", name="Matriz")
        self.other_store = Store.objects.create(company=company, code="02", name="Filial")
        self.product = Product.objects.create(
            store=self.store, internal_code="API001", name="Produto API", stock_quantity=Decimal("10"),
        )
        self.other_product = Product.objects.create(
            store=self.other_store, internal_code="API001", name="Produto outra unidade",
        )
        self.client = APIClient()
        self.client.force_authenticate(self.user)
        self.url = f"/api/me/stock-movements/?store_id={self.store.pk}"

    def post_movement(self, **overrides):
        data = dict(product_id=self.product.pk, movement_type="entry", quantity="2", reason="Entrada teste")
        data.update(overrides)
        return self.client.post(self.url, data, format="json")

    def assert_balance(self, expected):
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock_quantity, Decimal(expected))

    def test_entry_returns_history_and_updates_stock(self):
        response = self.post_movement()
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.data["balance_before"], "10.000")
        self.assertEqual(response.data["balance_after"], "12.000")
        self.assertEqual(response.data["created_by"], self.user.pk)
        self.assert_balance("12")

    def test_insufficient_stock_returns_400_without_changes(self):
        response = self.post_movement(movement_type="exit", quantity="11")
        self.assertEqual(response.status_code, 400)
        self.assert_balance("10")
        self.assertFalse(StockMovement.objects.exists())

    def test_adjustment_to_zero(self):
        response = self.post_movement(movement_type="adjustment", quantity="0")
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.data["quantity_change"], "-10.000")
        self.assert_balance("0")

    def test_invalid_inputs_are_rejected(self):
        for override in (
            {"quantity": "-1"}, {"quantity": "0"}, {"quantity": "0.0001"},
            {"quantity": "NaN"}, {"movement_type": "invalid"}, {"reason": "   "},
        ):
            with self.subTest(override=override):
                self.assertEqual(self.post_movement(**override).status_code, 400)
        self.assert_balance("10")
        self.assertFalse(StockMovement.objects.exists())

    def test_product_from_other_store_is_rejected(self):
        self.assertEqual(self.post_movement(product_id=self.other_product.pk).status_code, 400)
        self.assertFalse(StockMovement.objects.exists())

    def test_anonymous_is_denied(self):
        self.client.force_authenticate(user=None)
        self.assertIn(self.client.get(self.url).status_code, (401, 403))
        self.assertIn(self.post_movement().status_code, (401, 403))

    def test_unlinked_user_is_denied(self):
        user = get_user_model().objects.create_user(username="stock_api_unlinked")
        self.client.force_authenticate(user)
        self.assertEqual(self.client.get(self.url).status_code, 400)
        self.assertEqual(self.post_movement().status_code, 400)
        self.assertFalse(StockMovement.objects.exists())

    def test_history_is_scoped_to_store_and_product(self):
        self.post_movement()
        second = Product.objects.create(store=self.store, internal_code="API002", name="Segundo produto")
        register_stock_movement(
            user=self.user, store_id=self.store.pk, product_id=second.pk,
            movement_type="entry", quantity="1", reason="Segundo produto",
        )
        register_stock_movement(
            user=self.user, store_id=self.other_store.pk, product_id=self.other_product.pk,
            movement_type="entry", quantity="1", reason="Outra unidade",
        )