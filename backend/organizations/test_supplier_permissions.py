from uuid import uuid4
from django.contrib.auth.models import Permission,Group
from django.test import TestCase,RequestFactory
from django.core.exceptions import PermissionDenied
from django.contrib import admin
from . import test_suppliers as fixtures
from .models import Supplier,SupplierEvent
from .supplier_api import operate_supplier

class SupplierPermissionTests(TestCase):
    setUp=fixtures.SupplierTests.setUp
    grant=fixtures.SupplierTests.grant
    values=fixtures.SupplierTests.values
    path=fixtures.SupplierTests.path
    write=fixtures.SupplierTests.write
    create=fixtures.SupplierTests.create
    action=fixtures.SupplierTests.action

    def only(self,*codes):
        self.user.user_permissions.clear();self.grant(self.user,*codes)

    def test_editor_does_not_get_lifecycle_rights(self):
        record=self.create();self.only('view_supplier','change_supplier')
        self.action(record,'archive',reason='Duplicado',expected=403)
        saved=self.action(record,'update',name='Laboratório revisado')
        self.assertEqual(saved['name'],'Laboratório revisado');self.assertTrue(saved['is_active'])

    def test_archive_and_restore_are_independent_from_edit(self):
        record=self.create();self.only('view_supplier','archive_supplier')
        inactive=self.action(record,'archive',reason='Pausa')
        self.action(inactive,'restore',reason='Voltar',expected=403)
        self.action(inactive,'update',name='Forjado',expected=403)
        self.only('view_supplier','restore_supplier')
        active=self.action(inactive,'restore',reason='Retomada')
        self.assertTrue(active['is_active']);self.action(active,'archive',reason='Tentar',expected=403)

    def test_read_only_and_action_without_read_are_denied(self):
        record=self.create();self.only('view_supplier')
        self.assertEqual(self.client.get(self.path(record['id'])).status_code,200)
        self.action(record,'update',name='Outro',expected=403)
        self.only('archive_supplier');self.assertEqual(self.client.get(self.path(record['id'])).status_code,403)
        self.action(record,'archive',reason='Teste',expected=403)

    def test_group_revocation_and_retry_check_live_right(self):
        record=self.create();self.only('view_supplier')
        group=Group.objects.create(name='Arquivo fornecedor');group.permissions.add(Permission.objects.get(content_type__app_label='organizations',codename='archive_supplier'));self.user.groups.add(group)
        payload={'request_id':str(uuid4()),'action':'archive','expected_version':1,'reason':'Pausa'}
        self.write(payload,id=record['id']);group.permissions.clear();self.write(payload,id=record['id'],expected=403)
        self.assertEqual(SupplierEvent.objects.count(),2)
        with self.assertRaises(PermissionDenied):operate_supplier(user=self.user,store=self.store,supplier_id=record['id'],values=payload,digest='unused')

    def test_revoked_read_blocks_detail_admin_and_capabilities(self):
        record=self.create();self.user.is_staff=True;self.user.save()
        self.user.has_perm('organizations.view_supplier')
        self.user.user_permissions.remove(Permission.objects.get(content_type__app_label='organizations',codename='view_supplier'))
        self.assertEqual(self.client.get(self.path(record['id'])).status_code,403)
        request=RequestFactory().get('/admin/organizations/supplier/');request.user=self.user
        self.assertFalse(admin.site._registry[Supplier].has_view_permission(request))
        self.assertFalse(admin.site._registry[Supplier].get_queryset(request).exists())
        response=self.client.get(f'/api/me/suppliers/access/?store_id={self.store.pk}')
        self.assertEqual(response.status_code,200);self.assertFalse(any(response.data['actions'].values()))

    def test_malformed_action_cannot_create(self):
        self.grant()
        for action in ([],{},None,'delete'):self.write(self.values(action=action),expected=403)
        self.assertFalse(Supplier.objects.exists())
