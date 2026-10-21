from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from unittest import skipUnless
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import IntegrityError, close_old_connections, connection
from django.test import TestCase, TransactionTestCase
from rest_framework.test import APIClient

from organizations.models import Company, Store
from .models import StoreMembership, UserAccessEvent

User = get_user_model()
URL = "/api/me/user-management/"


class UserManagementTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.admin = User.objects.create_superuser(username="gestor", password="AdminFicticio!7642")
        cls.user = User.objects.create_user(username="operador", password="SenhaFicticia!4628")
        cls.company = Company.objects.create(name="Ótica Teste")
        cls.store = Store.objects.create(company=cls.company, code="G01", name="Matriz")
        cls.other = Store.objects.create(company=cls.company, code="G02", name="Filial")
        cls.permission = Permission.objects.get(content_type__app_label="organizations", codename="view_store")
        cls.technical = Permission.objects.get(content_type__app_label="accounts", codename="change_user")

    def setUp(self):
        self.client = APIClient()
        self.client.force_login(self.admin)

    def detail(self, user=None):
        return self.client.get(f"{URL}{(user or self.user).pk}/")

    def payload(self, **changes):
        response = self.detail()
        self.assertEqual(response.status_code, 200)
        record = response.data
        data = {name: record[name] for name in ("username", "first_name", "last_name", "email",
            "is_active", "permission_ids", "memberships", "version")}
        data.update(changes)
        return data

    def update(self, data):
        return self.client.patch(f"{URL}{self.user.pk}/", data, format="json")

    def create_payload(self, **changes):
        data = {"username": "novo_usuario", "first_name": "Nova", "last_name": "Pessoa",
                "email": "nova@example.test", "is_active": True,
                "permission_ids": [self.permission.pk],
                "memberships": [{"store_id": self.store.pk, "role": "seller", "is_active": True}],
                "password": "InicialFicticia!4628"}
        data.update(changes)
        return data

    def test_anonymous_and_normal_users_cannot_read_or_write(self):
        for actor in (None, self.user):
            self.client.logout()
            if actor:
                actor.is_staff = True
                actor.save()
                actor.user_permissions.add(self.technical)
                self.client.force_login(actor)
            for path in (URL, f"{URL}options/", f"{URL}{self.user.pk}/", f"{URL}{self.user.pk}/history/"):
                self.assertEqual(self.client.get(path).status_code, 403)
            self.assertEqual(self.client.post(URL, self.create_payload(), format="json").status_code, 403)
            self.assertEqual(self.client.patch(f"{URL}{self.user.pk}/", {}, format="json").status_code, 403)
            self.assertEqual(self.client.post(f"{URL}{self.user.pk}/password/", {}, format="json").status_code, 403)
        self.assertEqual(UserAccessEvent.objects.count(), 0)

    def test_inactive_administrator_and_revoked_superuser_are_denied(self):
        User.objects.filter(pk=self.admin.pk).update(is_active=False)
        self.assertEqual(self.client.get(URL).status_code, 403)
        User.objects.filter(pk=self.admin.pk).update(is_active=True, is_superuser=False)
        self.assertEqual(self.client.get(URL).status_code, 403)

    def test_options_are_global_and_catalog_excludes_technical_permissions(self):
        response = self.client.get(f"{URL}options/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual({s["id"] for s in response.data["stores"]}, {self.store.pk, self.other.pk})
        self.assertEqual(len(response.data["roles"]), 4)
        self.assertIn(self.permission.pk, [p["id"] for p in response.data["permissions"]])
        self.assertNotIn(self.technical.pk, [p["id"] for p in response.data["permissions"]])
        self.assertIn("no-store", response.headers["Cache-Control"])
        item = next(p for p in response.data["permissions"] if p["id"] == self.permission.pk)
        self.assertIn("Consultar", item["name"])

    def test_create_hashes_password_and_audits_without_credentials(self):
        data = self.create_payload()
        response = self.client.post(URL, data, format="json")
        self.assertEqual(response.status_code, 201, response.data)
        user = User.objects.get(pk=response.data["id"])
        self.assertTrue(user.check_password(data["password"]))
        self.assertFalse(user.is_staff or user.is_superuser)
        self.assertEqual(StoreMembership.objects.get(user=user).store_id, self.store.pk)
        self.assertTrue(user.has_perm("organizations.view_store"))
        text = str(response.data) + str(UserAccessEvent.objects.get(user=user).changes)
        self.assertNotIn(data["password"], text)
        self.assertNotIn(user.password, text)
        self.assertEqual(len(response.data["version"]), 64)

    def test_creation_does_not_grant_permissions_from_role(self):
        response = self.client.post(URL, self.create_payload(permission_ids=[]), format="json")
        self.assertEqual(response.status_code, 201, response.data)
        self.assertFalse(User.objects.get(pk=response.data["id"]).get_all_permissions())

    def test_unknown_privilege_fields_and_technical_permission_are_rejected(self):
        for field in ("is_superuser", "is_staff", "groups", "user_permissions", "theme", "id"):
            self.assertEqual(self.client.post(URL, self.create_payload(**{field: True}), format="json").status_code, 400)
        self.assertEqual(self.client.post(URL, self.create_payload(permission_ids=[self.technical.pk]), format="json").status_code, 400)
        invalid_member = {"store_id": self.store.pk, "role": "seller", "is_active": True, "user_id": self.admin.pk}
        self.assertEqual(self.client.post(URL, self.create_payload(memberships=[invalid_member]), format="json").status_code, 400)
        self.assertFalse(User.objects.filter(username="novo_usuario").exists())

    def test_invalid_passwords_username_email_and_roles_change_nothing(self):
        for changes in ({"password": "curta"}, {"username": "nome inválido"},
                        {"email": "invalido"}, {"memberships": [{"store_id": self.store.pk, "role": "root", "is_active": True}]}):
            response = self.client.post(URL, self.create_payload(**changes), format="json")
            self.assertEqual(response.status_code, 400, response.data)
        with self.settings(AUTH_PASSWORD_VALIDATORS=[{"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"}]):
            self.assertEqual(self.client.post(URL, self.create_payload(password="12345678"), format="json").status_code, 400)
        self.assertEqual(UserAccessEvent.objects.count(), 0)

    def test_duplicate_username_including_case_is_rejected(self):
        response = self.client.post(URL, self.create_payload(username="OPERADOR"), format="json")
        self.assertEqual(response.status_code, 400)
        self.assertEqual(User.objects.count(), 2)

    def test_missing_duplicate_or_inactive_store_is_rejected(self):
        self.other.is_active = False
        self.other.save()
        member = {"store_id": self.store.pk, "role": "seller", "is_active": True}
        for members in ([dict(member, store_id=999999)], [member, member], [dict(member, store_id=self.other.pk)], [dict(member, store_id=10 ** 80)]):
            response = self.client.post(URL, self.create_payload(memberships=members), format="json")
            self.assertEqual(response.status_code, 400, response.data)
        self.assertFalse(User.objects.filter(username="novo_usuario").exists())

    def test_edit_replaces_business_permissions_preserves_groups_and_technical_grants(self):
        group = Group.objects.create(name="Equipe")
        group.permissions.add(self.permission)
        self.user.groups.add(group)
        internal = Permission.objects.get(content_type__app_label="accounts", codename="add_useraccessevent")
        self.user.user_permissions.add(self.permission, self.technical, internal)
        response = self.update(self.payload(first_name="Atualizado", permission_ids=[]))
        self.assertEqual(response.status_code, 200, response.data)
        self.assertIn(self.permission.pk, response.data["inherited_permission_ids"])
        self.assertNotIn(self.permission.pk, response.data["permission_ids"])
        self.assertEqual(response.data["groups"], ["Equipe"])
        user = User.objects.get(pk=self.user.pk)
        self.assertTrue(user.has_perm("organizations.view_store"))
        self.assertTrue(user.has_perm("accounts.change_user"))
        self.assertTrue(user.user_permissions.filter(pk=internal.pk).exists())

    def test_omitted_membership_is_inactivated_without_deletion(self):
        member = StoreMembership.objects.create(user=self.user, store=self.store, role="seller")
        response = self.update(self.payload(memberships=[]))
        self.assertEqual(response.status_code, 200, response.data)
        member.refresh_from_db()
        self.assertFalse(member.is_active)
        response = self.update(self.payload(memberships=[{"store_id": self.store.pk, "role": "cashier", "is_active": True}]))
        self.assertEqual(response.status_code, 200, response.data)
        member.refresh_from_db()
        self.assertTrue(member.is_active)
        self.assertEqual(member.role, "cashier")
        self.assertEqual(StoreMembership.objects.filter(user=self.user).count(), 1)

    def test_inactive_old_store_can_be_preserved_or_revoked_not_granted(self):
        member = StoreMembership.objects.create(user=self.user, store=self.store, role="seller")
        self.store.is_active = False
        self.store.save()
        self.assertEqual(self.update(self.payload(first_name="Outro")).status_code, 200)
        self.assertEqual(self.update(self.payload(memberships=[])).status_code, 200)
        member.refresh_from_db()
        self.assertFalse(member.is_active)
        data = self.payload(memberships=[{"store_id": self.store.pk, "role": "seller", "is_active": True}])
        self.assertEqual(self.update(data).status_code, 400)

    def test_stale_or_missing_version_is_rejected_without_overwrite(self):
        data = self.payload(first_name="Primeiro")
        self.assertEqual(self.update(data).status_code, 200)
        data["first_name"] = "Segundo"
        self.assertEqual(self.update(data).status_code, 409)
        data.pop("version")
        self.assertEqual(self.update(data).status_code, 409)
        self.user.refresh_from_db()
        self.assertEqual(self.user.first_name, "Primeiro")
        self.assertEqual(UserAccessEvent.objects.count(), 1)

    def test_direct_admin_change_invalidates_version(self):
        data = self.payload()
        User.objects.filter(pk=self.user.pk).update(first_name="Alterado no admin")
        self.assertEqual(self.update(data).status_code, 409)

    def test_group_change_invalidates_version(self):
        data = self.payload()
        self.user.groups.add(Group.objects.create(name="Novo grupo"))
        self.assertEqual(self.update(data).status_code, 409)

    def test_superuser_including_self_cannot_be_modified_disabled_or_reset(self):
        record = self.detail(self.admin).data
        data = self.payload(username=self.admin.username, version=record["version"], is_active=False)
        self.assertEqual(self.client.patch(f"{URL}{self.admin.pk}/", data, format="json").status_code, 403)
        self.assertEqual(self.client.post(f"{URL}{self.admin.pk}/password/", {
            "version": record["version"], "password": "NovaFicticia!7548"}, format="json").status_code, 403)
        self.admin.refresh_from_db()
        self.assertTrue(self.admin.is_active and self.admin.is_superuser)

    def test_delete_and_unimplemented_methods_are_denied(self):
        self.assertEqual(self.client.delete(f"{URL}{self.user.pk}/").status_code, 405)
        self.assertEqual(self.client.put(f"{URL}{self.user.pk}/", {}, format="json").status_code, 405)
        self.assertTrue(User.objects.filter(pk=self.user.pk).exists())

    def test_inactivation_and_membership_revocation_apply_to_existing_session(self):
        member = StoreMembership.objects.create(user=self.user, store=self.store, role="seller")
        regular = APIClient()
        regular.force_login(self.user)
        self.assertEqual(len(regular.get("/api/me/stores/").data), 1)
        self.assertEqual(self.update(self.payload(memberships=[])).status_code, 200)
        self.assertEqual(regular.get("/api/me/stores/").data, [])
        member.refresh_from_db()
        self.assertFalse(member.is_active)
        self.assertEqual(self.update(self.payload(is_active=False)).status_code, 200)
        self.assertEqual(regular.get("/api/me/").status_code, 403)

    def test_reset_password_invalidates_session_and_previous_version(self):
        regular = APIClient()
        regular.force_login(self.user)
        record = self.detail().data
        response = self.client.post(f"{URL}{self.user.pk}/password/", {
            "password": "NovaFicticia!8345", "version": record["version"]}, format="json")
        self.assertEqual(response.status_code, 200, response.data)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password("NovaFicticia!8345"))
        self.assertEqual(regular.get("/api/me/").status_code, 403)
        self.assertEqual(UserAccessEvent.objects.get().action, "password_reset")
        self.assertEqual(UserAccessEvent.objects.get().changes, {})
        self.assertEqual(self.client.post(f"{URL}{self.user.pk}/password/", {
            "password": "NovaFicticia!8345", "version": record["version"]}, format="json").status_code, 409)

    def test_edit_endpoint_does_not_accept_password(self):
        self.assertEqual(self.update(self.payload(password="NovaFicticia!8345")).status_code, 400)

    def test_real_csrf_enforcement_for_all_mutations(self):
        client = APIClient(enforce_csrf_checks=True)
        client.force_login(self.admin)
        self.assertEqual(client.post(URL, self.create_payload(), format="json").status_code, 403)
        self.assertEqual(client.patch(f"{URL}{self.user.pk}/", self.payload(), format="json").status_code, 403)
        self.assertEqual(client.post(f"{URL}{self.user.pk}/password/", {}, format="json").status_code, 403)
        token = client.get("/api/auth/csrf/").json()["csrfToken"]
        self.assertEqual(client.post(URL, self.create_payload(), format="json", HTTP_X_CSRFTOKEN=token).status_code, 201)

    def test_audit_failure_rolls_back_user_permissions_and_memberships(self):
        original = self.payload()
        with patch("accounts.user_management_api.record_event", side_effect=RuntimeError("falha simulada")):
            with self.assertRaises(RuntimeError):
                self.update({**original, "first_name": "Não persistir", "permission_ids": [self.permission.pk],
                             "memberships": [{"store_id": self.store.pk, "role": "seller", "is_active": True}]})
        self.user.refresh_from_db()
        self.assertEqual(self.user.first_name, "")
        self.assertFalse(self.user.user_permissions.exists())
        self.assertFalse(StoreMembership.objects.filter(user=self.user).exists())

    def test_uniqueness_error_is_controlled(self):
        with patch("accounts.user_management_api.apply", side_effect=IntegrityError("simulado")):
            self.assertEqual(self.update(self.payload()).status_code, 400)
        self.assertEqual(UserAccessEvent.objects.count(), 0)

    def test_history_is_scoped_read_only_and_has_no_credentials(self):
        self.assertEqual(self.update(self.payload(first_name="Ana")).status_code, 200)
        other = User.objects.create_user(username="outro")
        UserAccessEvent.objects.create(user=other, actor=self.admin, action="updated")
        response = self.client.get(f"{URL}{self.user.pk}/history/")
        self.assertEqual(len(response.data["results"]), 1)
        item = response.data["results"][0]
        self.assertEqual(item["actor"], self.admin.username)
        self.assertEqual(item["changes"]["first_name"]["after"], "Ana")
        event = UserAccessEvent.objects.get(user=self.user)
        with self.assertRaises(DjangoValidationError):
            event.save()
        with self.assertRaises(DjangoValidationError):
            event.delete()
        self.assertEqual(self.client.post(f"{URL}{self.user.pk}/history/", {}, format="json").status_code, 405)

    def test_list_pagination_search_and_invalid_page(self):
        User.objects.bulk_create([User(username=f"teste_{i:02d}") for i in range(27)])
        response = self.client.get(URL)
        self.assertEqual(response.data["count"], 29)
        self.assertEqual(len(response.data["results"]), 25)
        self.assertTrue(response.data["has_next"])
        second = self.client.get(URL, {"page": 2})
        self.assertEqual(len(second.data["results"]), 4)
        self.assertFalse(second.data["has_next"])
        self.assertEqual(self.client.get(URL, {"search": "operador"}).data["count"], 1)
        for page in ("0", "-1", "a", "100001"):
            self.assertEqual(self.client.get(URL, {"page": page}).status_code, 400)

    def test_direct_permission_change_is_effective_without_new_login(self):
        self.assertEqual(self.update(self.payload(permission_ids=[self.permission.pk])).status_code, 200)
        self.assertTrue(User.objects.get(pk=self.user.pk).has_perm("organizations.view_store"))
        self.assertEqual(self.update(self.payload(permission_ids=[])).status_code, 200)
        self.assertFalse(User.objects.get(pk=self.user.pk).has_perm("organizations.view_store"))


@skipUnless(connection.vendor == "postgresql", "Exige locks reais do PostgreSQL")
class UserManagementConcurrencyTests(TransactionTestCase):
    def setUp(self):
        self.admins = [User.objects.create_superuser(username=f"gestor_{n}", password="AdminFicticio!7642") for n in range(2)]
        self.target = User.objects.create_user(username="alvo")

    def parallel(self, callback):
        barrier = Barrier(2)
        def worker(index):
            close_old_connections()
            try:
                client = APIClient()
                client.force_authenticate(User.objects.get(pk=self.admins[index].pk))
                barrier.wait(timeout=10)
                return callback(client, index)
            finally:
                close_old_connections()
        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(worker, index) for index in range(2)]
            return [future.result(timeout=30) for future in futures]

    def test_concurrent_edit_rejects_stale_version(self):
        client = APIClient()
        client.force_authenticate(self.admins[0])
        record = client.get(f"{URL}{self.target.pk}/").data
        payload = {name: record[name] for name in ("username", "first_name", "last_name", "email",
            "is_active", "permission_ids", "memberships", "version")}
        payload["first_name"] = "Alteração concorrente"
        statuses = self.parallel(lambda client, index: client.patch(f"{URL}{self.target.pk}/", payload, format="json").status_code)
        self.assertEqual(sorted(statuses), [200, 409])
        self.assertEqual(UserAccessEvent.objects.filter(user=self.target).count(), 1)

    def test_concurrent_create_keeps_one_case_insensitive_username(self):
        payload = {"first_name": "", "last_name": "", "email": "", "is_active": True,
                   "permission_ids": [], "memberships": [], "password": "SenhaFicticia!4628"}
        def create(client, index):
            username = "NovoConcorrente" if index == 0 else "novoconcorrente"
            return client.post(URL, {**payload, "username": username}, format="json").status_code
        self.assertEqual(sorted(self.parallel(create)), [201, 400])
        self.assertEqual(User.objects.filter(username__iexact="novoconcorrente").count(), 1)
