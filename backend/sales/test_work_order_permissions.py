from uuid import uuid4
from django.contrib.auth.models import Permission, Group
from django.core.exceptions import PermissionDenied
from django.test import TestCase
from . import test_work_orders as order_fixtures
from .work_order_services import operate_order

class OrderPermissionTests(TestCase):
    setUp=order_fixtures.ServiceOrderTests.setUp
    data=order_fixtures.ServiceOrderTests.data
    sale=order_fixtures.ServiceOrderTests.sale
    grant=order_fixtures.ServiceOrderTests.grant
    create=order_fixtures.ServiceOrderTests.create
    endpoint=order_fixtures.ServiceOrderTests.endpoint

    def only(self,*codes):
        self.user.user_permissions.remove(*Permission.objects.filter(content_type__app_label='sales',codename__endswith='_serviceorder'))
        self.grant(self.user,*codes)

    def post_action(self,order,action,**extra):
        order.refresh_from_db()
        return self.client.post(self.endpoint(order),{'request_id':str(uuid4()),'action':action,'expected_version':order.version,'reason':'Conferido',**extra},format='json')

    def test_editor_cannot_advance_rework_or_cancel(self):
        order,_=self.create();self.only('view_serviceorder','change_serviceorder')
        self.assertEqual(self.post_action(order,'update',laboratory='Novo').status_code,200)
        for action in ('advance','rework','cancel'):
            self.assertEqual(self.post_action(order,action).status_code,403)
        order.refresh_from_db();self.assertEqual(order.status,'open');self.assertEqual(order.events.count(),2)

    def test_operator_advances_without_edit_or_cancel(self):
        order,_=self.create();self.only('view_serviceorder','advance_serviceorder')
        response=self.post_action(order,'advance');self.assertEqual(response.status_code,200,response.data)
        self.assertTrue(response.data['actions']['advance']);self.assertFalse(response.data['actions']['update'])
        for action in ('update','cancel','rework'):
            self.assertEqual(self.post_action(order,action).status_code,403)

    def test_cancel_without_edit_preserves_sale(self):
        order,_=self.create();self.only('view_serviceorder','cancel_serviceorder')
        response=self.post_action(order,'cancel');self.assertEqual(response.status_code,200,response.data)
        order.sale.refresh_from_db();self.assertEqual(order.sale.status,'completed')
        self.assertFalse(any(response.data['actions'][key] for key in ('update','advance','rework','cancel')))

    def test_rework_without_edit_or_advance(self):
        order,_=self.create()
        for _ in range(3):self.assertEqual(self.post_action(order,'advance').status_code,200)
        self.only('view_serviceorder','rework_serviceorder')
        response=self.post_action(order,'rework',target_status='laboratory')
        self.assertEqual(response.status_code,200,response.data);self.assertEqual(response.data['status'],'laboratory')
        self.assertEqual(self.post_action(order,'advance').status_code,403)

    def test_read_only_and_no_permission(self):
        order,_=self.create();self.only('view_serviceorder')
        self.assertEqual(self.client.get(self.endpoint(order)).status_code,200)
        self.assertEqual(self.post_action(order,'update').status_code,403)
        self.only('advance_serviceorder')
        self.assertEqual(self.client.get(self.endpoint(order)).status_code,403)
        self.assertEqual(self.post_action(order,'advance').status_code,403)

    def test_replay_checks_revoked_action_and_cached_actor(self):
        order,_=self.create();self.user.has_perm('sales.advance_serviceorder')
        payload={'request_id':str(uuid4()),'action':'advance','expected_version':1}
        self.assertEqual(self.client.post(self.endpoint(order),payload,format='json').status_code,200)
        self.user.user_permissions.remove(Permission.objects.get(content_type__app_label='sales',codename='advance_serviceorder'))
        self.assertEqual(self.client.post(self.endpoint(order),payload,format='json').status_code,403)
        order.refresh_from_db();self.assertEqual(order.version,2)
        with self.assertRaises(PermissionDenied):
            operate_order(user=self.user,store=self.store,sale_id=order.sale_id,order_id=order.pk,values=payload,digest='unused')

    def test_group_revocation_is_immediate(self):
        order,_=self.create();self.only('view_serviceorder')
        group=Group.objects.create(name='Produção');group.permissions.add(Permission.objects.get(content_type__app_label='sales',codename='advance_serviceorder'));self.user.groups.add(group)
        self.assertEqual(self.post_action(order,'advance').status_code,200)
        group.permissions.clear()
        self.assertEqual(self.post_action(order,'advance').status_code,403)

    def test_creation_choices_do_not_require_sales_read_permission(self):
        sale=self.sale();self.only('view_serviceorder','add_serviceorder')
        self.user.user_permissions.remove(*Permission.objects.filter(content_type__app_label='sales',codename='view_sale'))
        response=self.client.get(f'/api/me/service-orders/sales/?store_id={self.store.pk}')
        self.assertEqual(response.status_code,200,response.data)
        self.assertEqual(response.data['results'],[{'id':sale.pk,'customer_name':self.customer.name}])
        payload={'request_id':str(uuid4()),'action':'create','sale_id':sale.pk,'promised_on':'2026-12-01'}
        self.assertEqual(self.client.post(self.endpoint(),payload,format='json').status_code,200)
        self.assertEqual(self.client.get(f'/api/me/service-orders/sales/?store_id={self.store.pk}').data['results'],[])
        self.only('view_serviceorder');self.assertEqual(self.client.get(f'/api/me/service-orders/sales/?store_id={self.store.pk}').status_code,403)

    def test_capabilities_and_unit_scoping(self):
        self.grant();url=f'/api/me/service-orders/access/?store_id={self.store.pk}'
        response=self.client.get(url);self.assertEqual(response.status_code,200,response.data)
        self.assertTrue(response.data['actions']['advance']);self.assertIn('no-store',response['Cache-Control'])
        self.assertIn(self.client.get(f'/api/me/service-orders/access/?store_id={self.other.pk}').status_code,(400,403))

    def test_unknown_action_is_denied_without_changes(self):
        order,_=self.create();self.assertEqual(self.post_action(order,'delete').status_code,403)
        self.assertEqual(order.events.count(),1)
