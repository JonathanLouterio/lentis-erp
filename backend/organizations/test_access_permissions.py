from decimal import Decimal

from django.contrib import admin
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission
from django.test import RequestFactory, TestCase
from rest_framework.test import APIClient

from accounts.models import StoreMembership
from .models import Company, Customer, Product, StockMovement, Store

User = get_user_model()


class CatalogPermissionsTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(username="permissoes")
        cls.company = Company.objects.create(name="Empresa Permissões")
        cls.store = Store.objects.create(company=cls.company, code="PM1", name="Matriz")
        cls.other = Store.objects.create(company=cls.company, code="PM2", name="Filial")
        StoreMembership.objects.create(user=cls.user, store=cls.store, role="seller")
        cls.customer = Customer.objects.create(store=cls.store, name="Cliente Matriz")
        cls.other_customer = Customer.objects.create(store=cls.other, name="Cliente Filial")
        cls.product = Product.objects.create(store=cls.store, internal_code="PM1", name="Produto Matriz",
            stock_quantity=Decimal("10"), cost_price=Decimal("120"), sale_price=Decimal("240"))
        cls.other_product = Product.objects.create(store=cls.other, internal_code="PM2", name="Produto Filial")

    def setUp(self):
        self.client = APIClient()
        self.client.force_authenticate(self.user)

    def grant(self, *codes):
        self.user.user_permissions.add(*Permission.objects.filter(
            content_type__app_label="organizations", codename__in=codes))

    def url(self, path, store=None):
        return f"/api/me/{path}/?store_id={(store or self.store).pk}"

    def write_movement(self):
        return self.client.post(self.url("stock-movements"), {
            "product_id": self.product.pk, "movement_type": "entry", "quantity": "2", "reason": "Conferência",
        }, format="json")

    def assert_stock_untouched(self):
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock_quantity, Decimal("10"))
        self.assertFalse(StockMovement.objects.exists())

    def test_anonymous_access_is_denied_including_new_endpoints(self):
        self.client.force_authenticate(user=None)
        for path in ("customers", "products", "stock-movements", "catalog-access", "stock-options"):
            self.assertEqual(self.client.get(self.url(path)).status_code, 403)
        self.assertEqual(self.write_movement().status_code, 403)
        self.assert_stock_untouched()

    def test_membership_without_permissions_does_not_allow_any_catalog_action(self):
        for plural, pk in (("customers", self.customer.pk), ("products", self.product.pk)):
            with self.subTest(plural=plural):
                self.assertEqual(self.client.get(self.url(plural)).status_code, 403)
                self.assertEqual(self.client.get(self.url(f"{plural}/{pk}")).status_code, 403)
                self.assertEqual(self.client.post(self.url(plural), {"name": "Bloqueado"}, format="json").status_code, 403)
                self.assertEqual(self.client.patch(self.url(f"{plural}/{pk}"), {"name": "Bloqueado"}, format="json").status_code, 403)
                self.assertEqual(self.client.delete(self.url(f"{plural}/{pk}")).status_code, 403)
        self.assertEqual(self.client.get(self.url("stock-movements")).status_code, 403)
        self.assertEqual(self.write_movement().status_code, 403)
        self.customer.refresh_from_db()
        self.product.refresh_from_db()
        self.assertTrue(self.customer.is_active and self.product.is_active)
        self.assertEqual(self.customer.name, "Cliente Matriz")
        self.assert_stock_untouched()

    def test_staff_and_every_membership_role_do_not_bypass_permissions(self):
        self.user.is_staff = True
        self.user.save()
        for role in StoreMembership.Role.values:
            StoreMembership.objects.filter(user=self.user).update(role=role)
            self.assertEqual(self.client.get(self.url("customers")).status_code, 403)
            self.assertEqual(self.client.delete(self.url(f"customers/{self.customer.pk}")).status_code, 403)
            self.assertEqual(self.client.delete(self.url(f"products/{self.product.pk}")).status_code, 403)
            self.assertEqual(self.write_movement().status_code, 403)

    def test_customer_view_allows_get_head_options_but_not_writes(self):
        self.grant("view_customer")
        self.assertEqual(self.client.get(self.url("customers")).status_code, 200)
        self.assertEqual(self.client.get(self.url(f"customers/{self.customer.pk}")).status_code, 200)
        self.assertEqual(self.client.head(self.url("customers")).status_code, 200)
        self.assertEqual(self.client.options(self.url("customers")).status_code, 200)
        self.assertEqual(self.client.post(self.url("customers"), {"name": "Novo"}, format="json").status_code, 403)
        self.assertEqual(self.client.patch(self.url(f"customers/{self.customer.pk}"), {"name": "Outro"}, format="json").status_code, 403)
        self.assertEqual(self.client.delete(self.url(f"customers/{self.customer.pk}")).status_code, 403)

    def test_customer_add_is_independent_from_consultation(self):
        self.grant("add_customer")
        self.assertEqual(self.client.get(self.url("customers")).status_code, 403)
        response = self.client.post(self.url("customers"), {"name": "Cadastro permitido"}, format="json")
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.data["store"], self.store.pk)
        self.assertEqual(self.client.patch(self.url(f"customers/{self.customer.pk}"), {"name": "Outro"}, format="json").status_code, 403)

    def test_customer_change_allows_patch_and_put_without_delete_or_create(self):
        self.grant("change_customer")
        url = self.url(f"customers/{self.customer.pk}")
        self.assertEqual(self.client.patch(url, {"name": "Editado"}, format="json").status_code, 200)
        self.assertEqual(self.client.put(url, {"name": "Substituído"}, format="json").status_code, 200)
        self.assertEqual(self.client.delete(url).status_code, 403)
        self.assertEqual(self.client.post(self.url("customers"), {"name": "Novo"}, format="json").status_code, 403)

    def test_customer_delete_permission_inactivates_even_without_staff(self):
        self.grant("delete_customer")
        self.assertFalse(self.user.is_staff)
        self.assertEqual(self.client.delete(self.url(f"customers/{self.customer.pk}")).status_code, 204)
        self.customer.refresh_from_db()
        self.assertFalse(self.customer.is_active)
        self.assertTrue(Customer.objects.filter(pk=self.customer.pk).exists())

    def test_product_view_does_not_allow_create_edit_or_archive(self):
        self.grant("view_product")
        self.assertEqual(self.client.get(self.url("products")).status_code, 200)
        self.assertEqual(self.client.head(self.url(f"products/{self.product.pk}")).status_code, 200)
        self.assertEqual(self.client.post(self.url("products"), {"name": "Novo", "internal_code": "N"}, format="json").status_code, 403)
        self.assertEqual(self.client.patch(self.url(f"products/{self.product.pk}"), {"name": "Outro"}, format="json").status_code, 403)
        self.assertEqual(self.client.delete(self.url(f"products/{self.product.pk}")).status_code, 403)

    def test_product_add_starts_with_zero_without_granting_view(self):
        self.grant("add_product")
        response = self.client.post(self.url("products"), {"name": "Novo", "internal_code": "NOVO"}, format="json")
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.data["stock_quantity"], "0.000")
        self.assertEqual(self.client.get(self.url("products")).status_code, 403)

    def test_product_change_cannot_edit_stock_or_inactivate(self):
        self.grant("change_product")
        url = self.url(f"products/{self.product.pk}")
        self.assertEqual(self.client.patch(url, {"name": "Editado"}, format="json").status_code, 200)
        self.assertEqual(self.client.put(url, {"name": "Atualizado", "internal_code": "PM1"}, format="json").status_code, 200)
        self.assertEqual(self.client.patch(url, {"stock_quantity": "999"}, format="json").status_code, 400)
        self.assertEqual(self.client.delete(url).status_code, 403)
        self.assert_stock_untouched()

    def test_product_delete_permission_inactivates_without_staff_and_preserves_stock(self):
        self.grant("delete_product")
        self.assertEqual(self.client.delete(self.url(f"products/{self.product.pk}")).status_code, 204)
        self.product.refresh_from_db()
        self.assertFalse(self.product.is_active)
        self.assertEqual(self.product.stock_quantity, Decimal("10"))
        self.assertTrue(Product.objects.filter(pk=self.product.pk).exists())

    def test_catalog_permissions_do_not_authorize_manual_stock(self):
        self.grant("view_product", "add_product", "change_product", "delete_product")
        self.assertEqual(self.write_movement().status_code, 403)
        self.assertEqual(self.client.get(self.url("stock-movements")).status_code, 403)
        self.assertEqual(self.client.get(self.url("stock-options")).status_code, 403)
        self.assert_stock_untouched()

    def test_stock_viewer_has_read_only_history_and_limited_product_selection(self):
        self.grant("view_stockmovement")
        self.assertEqual(self.client.get(self.url("stock-movements")).status_code, 200)
        response = self.client.get(self.url("stock-options"))
        self.assertEqual(response.status_code, 200, response.data)
        self.assertTrue(response.data["can_view"])
        self.assertFalse(response.data["can_create"])
        self.assertEqual(len(response.data["products"]), 1)
        self.assertEqual(set(response.data["products"][0]), {"id", "internal_code", "name", "stock_quantity", "minimum_stock"})
        self.assertEqual(self.client.get(self.url("products")).status_code, 403)
        self.assertEqual(self.write_movement().status_code, 403)
        self.assert_stock_untouched()

    def test_stock_creation_permission_is_independent_from_history_and_product_catalog(self):
        self.grant("add_stockmovement")
        options = self.client.get(self.url("stock-options"))
        self.assertTrue(options.data["can_create"])
        self.assertFalse(options.data["can_view"])
        response = self.write_movement()
        self.assertEqual(response.status_code, 201, response.data)
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock_quantity, Decimal("12"))
        self.assertEqual(self.client.get(self.url("stock-movements")).status_code, 403)
        self.assertEqual(self.client.get(self.url("products")).status_code, 403)

    def test_stock_history_cannot_be_edited_or_deleted_even_with_default_permissions(self):
        self.grant("view_stockmovement", "add_stockmovement", "change_stockmovement", "delete_stockmovement")
        self.assertEqual(self.write_movement().status_code, 201)
        self.assertEqual(self.client.delete(self.url("stock-movements")).status_code, 405)
        self.assertEqual(self.client.patch(self.url("stock-movements"), {}, format="json").status_code, 405)
        self.assertEqual(StockMovement.objects.count(), 1)

    def test_group_permissions_are_effective_and_revoked_in_existing_session(self):
        group = Group.objects.create(name="Consulta")
        group.permissions.add(Permission.objects.get(content_type__app_label="organizations", codename="view_customer"))
        self.user.groups.add(group)
        self.assertTrue(self.user.has_perm("organizations.view_customer"))  # Força cache no objeto antigo.
        self.assertEqual(self.client.get(self.url("customers")).status_code, 200)
        group.permissions.clear()
        self.assertEqual(self.client.get(self.url("customers")).status_code, 403)
        self.assertFalse(self.client.get(self.url("catalog-access")).data["customers"]["view"])

    def test_direct_permission_revocation_is_checked_fresh(self):
        self.grant("change_customer")
        self.assertTrue(self.user.has_perm("organizations.change_customer"))
        self.assertEqual(self.client.patch(self.url(f"customers/{self.customer.pk}"), {"name": "Antes"}, format="json").status_code, 200)
        self.user.user_permissions.clear()
        response = self.client.patch(self.url(f"customers/{self.customer.pk}"), {"name": "Depois"}, format="json")
        self.assertEqual(response.status_code, 403)
        self.customer.refresh_from_db()
        self.assertEqual(self.customer.name, "Antes")

    def test_permissions_never_bypass_membership_or_unit_scope(self):
        self.grant("view_customer", "change_customer", "delete_customer", "add_product", "view_product", "view_stockmovement", "add_stockmovement")
        self.assertEqual(self.client.get(self.url("customers", self.other)).status_code, 400)
        self.assertEqual(self.client.patch(self.url(f"customers/{self.other_customer.pk}"), {"name": "Invasão"}, format="json").status_code, 404)
        self.assertEqual(self.client.delete(self.url(f"customers/{self.other_customer.pk}")).status_code, 404)
        self.assertEqual(self.client.post(self.url("products", self.other), {"name": "X", "internal_code": "X"}, format="json").status_code, 400)
        self.assertEqual(self.client.get(self.url("stock-options", self.other)).status_code, 400)
        self.assertEqual(self.client.get(self.url("catalog-access", self.other)).status_code, 400)
        StoreMembership.objects.filter(user=self.user).update(is_active=False)
        self.assertEqual(self.client.get(self.url("customers")).status_code, 400)
        self.assertEqual(self.write_movement().status_code, 400)
        self.assert_stock_untouched()

    def test_inactive_user_store_or_company_blocks_existing_permissions(self):
        self.grant("view_customer", "add_stockmovement")
        User.objects.filter(pk=self.user.pk).update(is_active=False)
        self.assertEqual(self.client.get(self.url("customers")).status_code, 403)
        self.assertEqual(self.client.get(self.url("catalog-access")).status_code, 403)
        User.objects.filter(pk=self.user.pk).update(is_active=True)
        self.store.is_active = False
        self.store.save()
        self.assertEqual(self.client.get(self.url("customers")).status_code, 400)
        self.store.is_active = True
        self.store.save()
        self.company.is_active = False
        self.company.save()
        self.assertEqual(self.client.get(self.url("stock-options")).status_code, 400)
        self.assert_stock_untouched()

    def test_superuser_requires_active_entities_but_not_membership_or_explicit_grants(self):
        self.user.is_superuser = True
        self.user.save()
        StoreMembership.objects.filter(user=self.user).delete()
        self.assertEqual(self.client.get(self.url("customers", self.other)).status_code, 200)
        self.assertEqual(self.write_movement().status_code, 201)
        self.assertTrue(self.client.get(self.url("catalog-access")).data["customers"]["delete"])
        self.store.is_active = False
        self.store.save()
        self.assertEqual(self.client.get(self.url("stock-options")).status_code, 400)

    def test_metadata_has_only_own_capabilities_no_other_user_selection(self):
        self.grant("view_customer", "change_product")
        response = self.client.get(self.url("catalog-access") + "&user_id=999")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(set(response.data), {"store_id", "customers", "products", "stock"})
        self.assertEqual(response.data["customers"], {"view": True, "add": False, "change": False, "delete": False})
        self.assertTrue(response.data["products"]["change"])
        self.assertEqual(response.data["stock"], {"view": False, "add": False})
        self.assertIn("no-store", response.headers["Cache-Control"])

    def test_invalid_store_ids_and_missing_units_are_rejected(self):
        self.grant("view_customer", "view_stockmovement")
        for suffix in ("", "?store_id=x", "?store_id=-1", f"?store_id={10 ** 80}"):
            self.assertEqual(self.client.get("/api/me/catalog-access/" + suffix).status_code, 400)
            self.assertEqual(self.client.get("/api/me/stock-options/" + suffix).status_code, 400)

    def test_stock_options_exclude_inactive_and_other_unit_products(self):
        self.grant("view_stockmovement")
        self.product.is_active = False
        self.product.save()
        response = self.client.get(self.url("stock-options"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["products"], [])

    def test_real_csrf_required_even_with_all_action_permissions(self):
        self.grant("add_customer", "change_customer", "delete_customer", "add_product", "change_product", "delete_product", "add_stockmovement")
        client = APIClient(enforce_csrf_checks=True)
        client.force_login(self.user)
        self.assertEqual(client.post(self.url("customers"), {"name": "Novo"}, format="json").status_code, 403)
        self.assertEqual(client.patch(self.url(f"customers/{self.customer.pk}"), {"name": "X"}, format="json").status_code, 403)
        self.assertEqual(client.delete(self.url(f"products/{self.product.pk}")).status_code, 403)
        self.assertEqual(client.post(self.url("stock-movements"), {}, format="json").status_code, 403)
        token = client.get("/api/auth/csrf/").json()["csrfToken"]
        response = client.post(self.url("customers"), {"name": "Com CSRF"}, format="json", HTTP_X_CSRFTOKEN=token)
        self.assertEqual(response.status_code, 201, response.data)
        self.assert_stock_untouched()


    def test_state_flag_cannot_bypass_inactivation_permission(self):
        self.grant("add_customer", "change_customer", "add_product", "change_product")
        for resource, pk in (("customers", self.customer.pk), ("products", self.product.pk)):
            response = self.client.patch(self.url(f"{resource}/{pk}"), {"is_active": False}, format="json")
            self.assertEqual(response.status_code, 400, response.data)
            self.assertIn("is_active", response.data)
            response = self.client.post(self.url(resource), {"name": "Inativo", "internal_code": "INAT", "is_active": False}, format="json")
            self.assertEqual(response.status_code, 400, response.data)
        self.customer.refresh_from_db()
        self.product.refresh_from_db()
        self.assertTrue(self.customer.is_active and self.product.is_active)

    def test_django_admin_catalog_maintenance_requires_superuser(self):
        self.user.is_staff = True
        self.user.save()
        self.grant("view_customer", "add_customer", "change_customer", "delete_customer", "view_product", "add_product", "change_product", "delete_product")
        for model in (Customer, Product):
            request = RequestFactory().get("/admin/")
            request.user = self.user
            model_admin = admin.site._registry[model]
            self.assertFalse(model_admin.has_module_permission(request))
            self.assertFalse(model_admin.has_view_permission(request))
            self.assertFalse(model_admin.has_change_permission(request))
            self.assertFalse(model_admin.has_add_permission(request))
            self.assertFalse(model_admin.get_queryset(request).exists())
        self.user.is_superuser = True
        self.user.save()
        request = RequestFactory().get("/admin/")
        request.user = self.user
        self.assertTrue(admin.site._registry[Customer].has_change_permission(request))
        self.assertTrue(admin.site._registry[Product].has_view_permission(request))
