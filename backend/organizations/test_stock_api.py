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
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data), 2)
        filtered = self.client.get(f"{self.url}&product_id={self.product.pk}")
        self.assertEqual(len(filtered.data), 1)
        self.assertEqual(filtered.data[0]["product"], self.product.pk)

    def test_forged_author_and_balances_are_ignored(self):
        response = self.post_movement(
            created_by=999, store=self.other_store.pk, balance_before="999", balance_after="999",
        )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data["store"], self.store.pk)
        self.assertEqual(response.data["created_by"], self.user.pk)
        self.assertEqual(response.data["balance_after"], "12.000")

    def test_history_remains_when_product_is_inactive(self):
        self.post_movement()
        self.product.is_active = False
        self.product.save(update_fields=["is_active"])
        self.assertEqual(len(self.client.get(self.url).data), 1)
        self.assertEqual(self.post_movement().status_code, 400)

    def test_history_cannot_be_updated_or_deleted(self):
        self.post_movement()
        self.assertEqual(self.client.patch(self.url, {"reason": "Edit"}, format="json").status_code, 405)
        self.assertEqual(self.client.delete(self.url).status_code, 405)

    def test_bad_store_or_product_filter_returns_400(self):
        self.assertEqual(self.client.get("/api/me/stock-movements/?store_id=abc").status_code, 400)
        self.assertEqual(self.client.get(f"{self.url}&product_id=abc").status_code, 400)

    def test_direct_stock_change_is_rejected(self):
        url = f"/api/me/products/{self.product.pk}/?store_id={self.store.pk}"
        response = self.client.patch(url, {"stock_quantity": "999"}, format="json")
        self.assertEqual(response.status_code, 400)
        self.assert_balance("10")

    def test_new_product_starts_at_zero(self):
        url = f"/api/me/products/?store_id={self.store.pk}"
        response = self.client.post(url, {"internal_code": "NEW001", "name": "Novo"}, format="json")
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.data["stock_quantity"], "0.000")
        response = self.client.post(
            url, {"internal_code": "NEW002", "name": "Outro", "stock_quantity": "5"}, format="json",
        )
        self.assertEqual(response.status_code, 400)

    def test_stale_product_edit_does_not_overwrite_stock(self):
        serializer = ProductSerializer(self.product, data={"name": "Renomeado"}, partial=True)
        self.assertTrue(serializer.is_valid(), serializer.errors)
        self.post_movement()
        serializer.save()
        self.assert_balance("12")
        self.assertEqual(self.product.name, "Renomeado")

    def test_post_without_csrf_is_denied(self):
        client = APIClient(enforce_csrf_checks=True)
        client.force_login(self.user)
        response = client.post(
            self.url, {"product_id": self.product.pk, "movement_type": "entry", "quantity": "1", "reason": "Teste"},
            format="json",
        )
        self.assertEqual(response.status_code, 403)
        self.assertFalse(StockMovement.objects.exists())

    def test_admin_history_is_read_only(self):
        model_admin = admin.site._registry[StockMovement]
        request = RequestFactory().get("/admin/")
        request.user = self.user
        self.assertFalse(model_admin.has_add_permission(request))
        self.assertFalse(model_admin.has_change_permission(request))
        self.assertFalse(model_admin.has_delete_permission(request))

    def test_admin_product_edit_preserves_latest_balance(self):
        stale = Product.objects.get(pk=self.product.pk)
        self.post_movement()
        stale.name = "Nome atualizado pelo admin"
        model_admin = admin.site._registry[Product]
        request = RequestFactory().get("/admin/")
        request.user = self.user
        model_admin.save_model(request, stale, form=None, change=True)
        self.assert_balance("12")
        self.assertIn("stock_quantity", model_admin.get_readonly_fields(request, stale))
        self.assertIn("store", model_admin.get_readonly_fields(request, stale))
