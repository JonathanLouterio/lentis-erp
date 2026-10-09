from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from accounts.models import StoreMembership
from organizations.models import Company, Customer, Product, StockMovement, Store

from .models import FinancialAccount, PaymentMethod, Sale, SaleItem, SalePayment
from .services import finalize_sale


class SalesAPITests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username="sales_api", password="test-only-password")
        self.admin = get_user_model().objects.create_user(username="sales_admin", is_staff=True)
        company = Company.objects.create(name="Empresa API vendas")
        self.store = Store.objects.create(company=company, code="01", name="Matriz", allow_negative_stock=False)
        self.other_store = Store.objects.create(company=company, code="02", name="Filial")
        self.membership = StoreMembership.objects.create(user=self.user, store=self.store, role=StoreMembership.Role.SELLER)
        StoreMembership.objects.create(user=self.admin, store=self.store, role=StoreMembership.Role.SELLER)
        self.customer = Customer.objects.create(store=self.store, name="Cliente API")
        self.other_customer = Customer.objects.create(store=self.other_store, name="Outro cliente")
        self.product = Product.objects.create(
            store=self.store, internal_code="SA001", name="Armação", sale_price=Decimal("100"), stock_quantity=Decimal("10"),
        )
        self.other_product = Product.objects.create(store=self.other_store, internal_code="SA002", name="Outro produto")
        self.sale = Sale.objects.create(store=self.store, created_by=self.user)
        self.other_sale = Sale.objects.create(store=self.other_store, created_by=self.user)
        self.account = FinancialAccount.objects.create(store=self.store, code="cash", name="Caixa")
        self.method = PaymentMethod.objects.create(store=self.store, code="cash", name="Dinheiro", kind="cash")
        self.client = APIClient()
        self.client.force_authenticate(self.user)

    def url(self, suffix="", *, sale=None, store=None):
        base = "/api/me/sales/"
        if sale is not None:
            base += f"{sale.pk}/"
        return f"{base}{suffix}?store_id={(store or self.store).pk}"

    def add_item(self, sale=None, **overrides):
        values = {"sale": sale or self.sale, "product": self.product, "quantity": Decimal("2")}
        values.update(overrides)
        item = SaleItem.objects.create(**values)
        sale = values["sale"]
        if sale.total > 0:
            SalePayment.objects.create(sale=sale, method=self.method, account=self.account, amount=sale.total, first_due_date=date(2026, 10, 8), confirmed=True)
        return item

    def test_anonymous_is_denied(self):
        self.client.force_authenticate(None)
        self.assertEqual(self.client.get(self.url()).status_code, 403)
        self.assertEqual(self.client.post(self.url(), {}, format="json").status_code, 403)

    def test_store_is_required_and_must_be_authorized(self):
        for url in ("/api/me/sales/", "/api/me/sales/?store_id=abc", self.url(store=self.other_store)):
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url).status_code, 400)

    def test_create_uses_server_unit_author_status_and_totals(self):
        response = self.client.post(self.url(), {
            "store": self.other_store.pk, "created_by": self.admin.pk, "status": "completed", "total": "9000",
            "notes": "Balcão",
        }, format="json")
        self.assertEqual(response.status_code, 201, response.data)
        sale = Sale.objects.get(pk=response.data["id"])
        self.assertEqual((sale.store_id, sale.created_by_id, sale.status), (self.store.pk, self.user.pk, "draft"))
        self.assertIsNone(sale.customer_id)
        self.assertEqual(response.data["total"], "0.00")
        self.assertFalse(response.data["can_finalize"])
        self.assertFalse(StockMovement.objects.exists())

    def test_nested_items_capture_price_and_calculate_totals(self):
        response = self.client.post(self.url(), {
            "customer_id": self.customer.pk,
            "items": [{"product_id": self.product.pk, "quantity": "2.500", "discount_amount": "10.00"}],
        }, format="json")
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.data["customer_name"], self.customer.name)
        self.assertEqual(response.data["items"][0]["unit_price"], "100.00")
        self.assertEqual(response.data["total"], "240.00")
        self.assertTrue(response.data["can_finalize"])
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock_quantity, Decimal("10"))

    def test_invalid_nested_item_rolls_back_whole_sale(self):
        count = Sale.objects.count()
        response = self.client.post(self.url(), {
            "items": [
                {"product_id": self.product.pk},
                {"product_id": self.product.pk, "discount_amount": "1000"},
            ],
        }, format="json")
        self.assertEqual(response.status_code, 400, response.data)
        self.assertEqual(Sale.objects.count(), count)
        self.assertFalse(SaleItem.objects.exists())

    def test_customer_must_be_active_and_in_selected_store(self):
        self.customer.is_active = False
        self.customer.save(update_fields=["is_active"])
        for customer in (self.customer, self.other_customer):
            with self.subTest(customer=customer.pk):
                response = self.client.post(self.url(), {"customer_id": customer.pk}, format="json")
                self.assertEqual(response.status_code, 400)

    def test_product_must_be_active_and_in_selected_store(self):
        self.product.is_active = False
        self.product.save(update_fields=["is_active"])
        for product in (self.product, self.other_product):
            with self.subTest(product=product.pk):
                response = self.client.post(self.url("items/", sale=self.sale), {"product_id": product.pk}, format="json")
                self.assertEqual(response.status_code, 400)

    def test_list_is_paginated_and_scoped_to_selected_store(self):
        response = self.client.get(self.url())
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["count"], 1)
        self.assertEqual([sale["id"] for sale in response.data["results"]], [self.sale.pk])

    def test_status_filter_is_validated(self):
        response = self.client.get(self.url() + "&status=completed")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["count"], 0)
        self.assertEqual(self.client.get(self.url() + "&status=invalid").status_code, 400)

    def test_sale_from_other_unit_cannot_be_read_changed_or_finalized(self):
        for method, suffix in (("get", ""), ("patch", ""), ("post", "finalize/"), ("post", "cancel/")):
            with self.subTest(method=method, suffix=suffix):
                url = self.url(suffix, sale=self.other_sale)
                response = self.client.get(url) if method == "get" else getattr(self.client, method)(url, {"reason": "Teste"}, format="json")
                self.assertEqual(response.status_code, 404)

    def test_draft_customer_and_notes_can_be_changed(self):
        response = self.client.patch(self.url(sale=self.sale), {"customer_id": self.customer.pk, "notes": "Entrega amanhã"}, format="json")
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["customer"], self.customer.pk)
        response = self.client.patch(self.url(sale=self.sale), {"customer_id": None}, format="json")
        self.assertIsNone(response.data["customer"])
        self.assertEqual(response.data["notes"], "Entrega amanhã")

    def test_patch_cannot_finalize_or_change_sale_ownership(self):
        response = self.client.patch(self.url(sale=self.sale), {
            "status": "completed", "store": self.other_store.pk, "created_by": self.admin.pk, "total": "123",
        }, format="json")
        self.assertEqual(response.status_code, 200, response.data)
        self.sale.refresh_from_db()
        self.assertEqual((self.sale.status, self.sale.store_id, self.sale.created_by_id), ("draft", self.store.pk, self.user.pk))
        self.assertFalse(StockMovement.objects.exists())

    def test_item_can_be_added_edited_and_removed(self):
        response = self.client.post(self.url("items/", sale=self.sale), {"product_id": self.product.pk}, format="json")
        self.assertEqual(response.status_code, 201, response.data)
        item = self.sale.items.get()
        url = self.url(f"items/{item.pk}/", sale=self.sale)
        response = self.client.patch(url, {"quantity": "3", "unit_price": "90", "discount_amount": "20"}, format="json")
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["total"], "250.00")
        response = self.client.delete(url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["total"], "0.00")
        self.assertFalse(self.sale.items.exists())

    def test_duplicate_item_is_rejected_without_changes(self):
        self.add_item()
        response = self.client.post(self.url("items/", sale=self.sale), {"product_id": self.product.pk}, format="json")
        self.assertEqual(response.status_code, 400, response.data)
        self.assertEqual(self.sale.items.count(), 1)

    def test_foreign_item_cannot_be_changed_or_removed(self):
        other = Sale.objects.create(store=self.store, created_by=self.user)
        item = self.add_item(sale=other)
        url = self.url(f"items/{item.pk}/", sale=self.sale)
        self.assertEqual(self.client.patch(url, {"quantity": "1"}, format="json").status_code, 404)
        self.assertEqual(self.client.delete(url).status_code, 404)
        self.assertTrue(SaleItem.objects.filter(pk=item.pk).exists())

    def test_invalid_item_values_do_not_change_item(self):
        item = self.add_item()
        for values in ({"quantity": "0"}, {"unit_price": "-1"}, {"quantity": "1.0001"}, {"discount_amount": "201"}):
            with self.subTest(values=values):
                response = self.client.patch(self.url(f"items/{item.pk}/", sale=self.sale), values, format="json")
                self.assertEqual(response.status_code, 400, response.data)
        item.refresh_from_db()
        self.assertEqual(item.quantity, Decimal("2"))
        self.assertEqual(item.discount_amount, Decimal("0"))

    def test_finalize_updates_stock_once_and_returns_audit(self):
        self.add_item()
        for _ in range(2):
            response = self.client.post(self.url("finalize/", sale=self.sale), {}, format="json")
            self.assertEqual(response.status_code, 200, response.data)
            self.assertEqual(response.data["status"], "completed")
            self.assertFalse(response.data["can_edit"])
            self.assertFalse(response.data["can_cancel"])
            self.assertEqual(response.data["events"][0]["created_by"], self.user.pk)
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock_quantity, Decimal("8"))
        self.assertEqual(StockMovement.objects.count(), 1)

    def test_empty_or_insufficient_sale_cannot_finalize(self):
        response = self.client.post(self.url("finalize/", sale=self.sale), {}, format="json")
        self.assertEqual(response.status_code, 400)
        self.add_item(quantity=Decimal("11"))
        response = self.client.post(self.url("finalize/", sale=self.sale), {}, format="json")
        self.assertEqual(response.status_code, 400)
        self.sale.refresh_from_db()
        self.assertEqual(self.sale.status, "draft")
        self.assertFalse(StockMovement.objects.exists())

    def test_completed_sale_and_items_cannot_be_edited(self):
        item = self.add_item()
        finalize_sale(user=self.user, sale_id=self.sale.pk)
        responses = [
            self.client.patch(self.url(sale=self.sale), {"notes": "Alterar"}, format="json"),
            self.client.post(self.url("items/", sale=self.sale), {"product_id": self.product.pk}, format="json"),
            self.client.patch(self.url(f"items/{item.pk}/", sale=self.sale), {"quantity": "1"}, format="json"),
            self.client.delete(self.url(f"items/{item.pk}/", sale=self.sale)),
        ]
        for response in responses:
            self.assertEqual(response.status_code, 400, response.data)
        item.refresh_from_db()
        self.assertEqual(item.quantity, Decimal("2"))

    def test_seller_can_cancel_draft_but_cannot_cancel_completed_sale(self):
        response = self.client.post(self.url("cancel/", sale=self.sale), {"reason": "Desistência"}, format="json")
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["status"], "cancelled")
        self.assertFalse(StockMovement.objects.exists())
        sale = Sale.objects.create(store=self.store, created_by=self.user)
        self.add_item(sale=sale)
        finalize_sale(user=self.user, sale_id=sale.pk)
        response = self.client.post(self.url("cancel/", sale=sale), {"reason": "Devolução"}, format="json")
        self.assertEqual(response.status_code, 403)
        sale.refresh_from_db()
        self.assertEqual(sale.status, "completed")

    def test_admin_cancellation_returns_stock_once_and_preserves_history(self):
        self.add_item()
        finalize_sale(user=self.user, sale_id=self.sale.pk)
        self.client.force_authenticate(self.admin)
        for _ in range(2):
            response = self.client.post(self.url("cancel/", sale=self.sale), {"reason": "Devolução"}, format="json")
            self.assertEqual(response.status_code, 200, response.data)
            self.assertEqual(response.data["status"], "cancelled")
            self.assertEqual(response.data["cancellation_reason"], "Devolução")
            self.assertEqual(len(response.data["events"]), 2)
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock_quantity, Decimal("10"))
        self.assertEqual(StockMovement.objects.count(), 2)

    def test_cancel_requires_reason_and_sale_cannot_be_deleted(self):
        for data in ({}, {"reason": " "}, {"reason": "x" * 256}):
            self.assertEqual(self.client.post(self.url("cancel/", sale=self.sale), data, format="json").status_code, 400)
        self.assertEqual(self.client.delete(self.url(sale=self.sale)).status_code, 405)
        self.sale.refresh_from_db()
        self.assertEqual(self.sale.status, "draft")

    def test_revoked_membership_blocks_existing_authenticated_client(self):
        self.membership.is_active = False
        self.membership.save(update_fields=["is_active"])
        self.assertEqual(self.client.get(self.url()).status_code, 400)
        self.assertEqual(self.client.post(self.url("finalize/", sale=self.sale), {}, format="json").status_code, 400)

    def test_session_writes_without_csrf_are_denied_without_changes(self):
        item = self.add_item()
        client = APIClient(enforce_csrf_checks=True)
        client.force_login(self.user)
        count = Sale.objects.count()
        operations = [
            ("post", self.url(), {}),
            ("patch", self.url(sale=self.sale), {"notes": "Alterar"}),
            ("post", self.url("items/", sale=self.sale), {"product_id": self.product.pk}),
            ("patch", self.url(f"items/{item.pk}/", sale=self.sale), {"quantity": "1"}),
            ("delete", self.url(f"items/{item.pk}/", sale=self.sale), {}),
            ("post", self.url("finalize/", sale=self.sale), {}),
            ("post", self.url("cancel/", sale=self.sale), {"reason": "Teste"}),
        ]
        for method, url, data in operations:
            with self.subTest(method=method, url=url):
                response = getattr(client, method)(url, data, format="json")
                self.assertEqual(response.status_code, 403)
        self.sale.refresh_from_db()
        item.refresh_from_db()
        self.assertEqual(Sale.objects.count(), count)
        self.assertEqual(self.sale.status, "draft")
        self.assertEqual(self.sale.notes, "")
        self.assertEqual(item.quantity, Decimal("2"))
        self.assertFalse(StockMovement.objects.exists())

    def test_session_write_with_csrf_succeeds(self):
        client = APIClient(enforce_csrf_checks=True)
        client.force_login(self.user)
        token = "a" * 32
        client.cookies["csrftoken"] = token
        response = client.post(self.url(), {"notes": "Com CSRF"}, format="json", HTTP_X_CSRFTOKEN=token)
        self.assertEqual(response.status_code, 201, response.data)
