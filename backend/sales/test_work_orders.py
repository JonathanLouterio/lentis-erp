from uuid import uuid4
from unittest.mock import patch
from django.contrib.auth.models import Permission
from django.core.exceptions import ValidationError
from django.test import TestCase
from rest_framework.test import APIClient
from . import test_payments as fixtures
from .models import ServiceOrder, ServiceOrderEvent, Sale, FinancialEntry
from organizations.models import StockMovement


class ServiceOrderTests(TestCase):
    setUp = fixtures.PaymentCheckoutTests.setUp
    data = fixtures.PaymentCheckoutTests.data

    def grant(self, user=None, *codes):
        user = user or self.user
        codes = codes or ('view_serviceorder','add_serviceorder','change_serviceorder')
        user.user_permissions.add(*Permission.objects.filter(content_type__app_label='sales',codename__in=codes))
        for attr in ('_perm_cache','_user_perm_cache','_group_perm_cache'):
            if hasattr(user,attr):delattr(user,attr)

    def sale(self):
        response=self.client.post(self.url,self.data(),format='json')
        self.assertEqual(response.status_code,200,response.data)
        return Sale.objects.get(pk=response.data['id'])

    def endpoint(self, order=None, store=None):
        return f'/api/me/service-orders/{str(order.pk)+"/" if order else ""}?store_id={(store or self.store).pk}'

    def create(self, sale=None, **extra):
        self.grant()
        sale=sale or self.sale()
        data={'request_id':str(uuid4()),'action':'create','sale_id':sale.pk,'promised_on':'2026-01-01','laboratory':'Laboratório teste',**extra}
        response=self.client.post(self.endpoint(),data,format='json')
        self.assertEqual(response.status_code,200,response.data)
        return ServiceOrder.objects.get(pk=response.data['id']),data

    def operate(self,order,action='advance',expected=200,**extra):
        order.refresh_from_db()
        data={'request_id':str(uuid4()),'action':action,'expected_version':order.version,**extra}
        response=self.client.post(self.endpoint(order),data,format='json')
        self.assertEqual(response.status_code,expected,response.data)
        return response,data

    def test_creation_preserves_items_and_does_not_move_stock_or_finances(self):
        sale=self.sale();stock=StockMovement.objects.count();money=FinancialEntry.objects.count()
        order,_=self.create(sale)
        self.assertEqual(order.snapshot['customer_name'],self.customer.name)
        self.assertEqual(order.snapshot['items'][0]['name'],self.product.name)
        self.assertEqual(StockMovement.objects.count(),stock);self.assertEqual(FinancialEntry.objects.count(),money)
        self.assertEqual(order.events.count(),1)
        self.customer.name='Nome alterado';self.customer.save()
        order.refresh_from_db();self.assertNotEqual(order.snapshot['customer_name'],self.customer.name)

    def test_create_requires_finalized_sale_and_identified_customer(self):
        self.grant();sale=Sale.objects.create(store=self.store,created_by=self.user,customer=self.customer)
        data={'request_id':str(uuid4()),'action':'create','sale_id':sale.pk,'promised_on':'2026-11-01'}
        self.assertEqual(self.client.post(self.endpoint(),data,format='json').status_code,400)
        self.assertFalse(ServiceOrder.objects.exists())
        Sale.objects.filter(pk=sale.pk).update(customer=None,status='completed',completed_at=__import__('django').utils.timezone.now())
        self.assertEqual(self.client.post(self.endpoint(),data,format='json').status_code,400)

    def test_complete_lifecycle_requires_confirmation_and_recipient(self):
        order,_=self.create()
        for state in ['laboratory','mounting','checking']:
            response,_=self.operate(order);self.assertEqual(response.data['status'],state)
        self.operate(order,expected=400)
        self.operate(order,confirmed=True)
        self.operate(order,confirmed=True,expected=400)
        response,_=self.operate(order,confirmed=True,reason='Entregue para Maria, cliente')
        self.assertEqual(response.data['status'],'delivered')
        self.operate(order,'update',reason='Tentativa',expected=400)
        self.assertEqual(order.events.count(),6)

    def test_rework_needs_reason_and_permitted_origin(self):
        order,_=self.create()
        self.operate(order,'rework',target_status='laboratory',reason='Refazer',expected=400)
        for _ in range(3):self.operate(order)
        self.operate(order,'rework',target_status='laboratory',expected=400)
        response,_=self.operate(order,'rework',target_status='laboratory',reason='Revisar acabamento')
        self.assertEqual(response.data['status'],'laboratory')

    def test_stale_update_and_same_request_with_changed_payload_are_rejected(self):
        order,_=self.create();version=order.version
        self.operate(order,'update',reason='Ajusta prazo',promised_on='2026-12-01')
        data={'request_id':str(uuid4()),'action':'advance','expected_version':version}
        self.assertEqual(self.client.post(self.endpoint(order),data,format='json').status_code,400)
        _,request=self.operate(order)
        request['reason']='Outro conteúdo'
        self.assertEqual(self.client.post(self.endpoint(order),request,format='json').status_code,400)

    def test_retry_does_not_duplicate_order_or_event(self):
        order,data=self.create()
        self.assertEqual(self.client.post(self.endpoint(),data,format='json').status_code,200)
        self.assertEqual(ServiceOrder.objects.count(),1);self.assertEqual(order.events.count(),1)
        _,data=self.operate(order)
        self.assertEqual(self.client.post(self.endpoint(order),data,format='json').status_code,200)
        self.assertEqual(order.events.count(),2)
        data={'request_id':str(uuid4()),'action':'create','sale_id':order.sale_id,'promised_on':'2026-11-01'}
        self.assertEqual(self.client.post(self.endpoint(),data,format='json').status_code,400)

    def test_permissions_staff_and_unit_isolation(self):
        sale=self.sale()
        self.assertEqual(self.client.get(self.endpoint()).status_code,403)
        self.client.force_authenticate(self.admin)
        self.assertEqual(self.client.get(self.endpoint()).status_code,403)
        self.client.force_authenticate(self.user);order,_=self.create(sale)
        self.assertIn(self.client.get(self.endpoint(order,self.other)).status_code,(400,403))
        self.grant(self.admin,'view_serviceorder');self.client.force_authenticate(self.admin)
        self.assertEqual(self.client.get(self.endpoint(order)).status_code,200)
        self.operate(order,expected=403)
        self.client.force_authenticate(None)
        self.assertEqual(self.client.get(self.endpoint()).status_code,403)

    def test_cancel_is_independent_and_cancelled_sale_blocks_progress(self):
        order,_=self.create();sale=order.sale
        Sale.objects.filter(pk=sale.pk).update(status='cancelled',cancelled_at=__import__('django').utils.timezone.now(),cancellation_reason='Desistência')
        self.operate(order,expected=400)
        self.operate(order,'cancel',expected=400)
        response,_=self.operate(order,'cancel',reason='Venda cancelada, interromper produção')
        self.assertEqual(response.data['status'],'cancelled');self.assertEqual(order.events.count(),2)
        self.operate(order,expected=400)

    def test_rollback_keeps_state_and_history_when_event_fails(self):
        order,_=self.create()
        with patch('sales.work_order_services.ServiceOrderEvent.objects.create',side_effect=RuntimeError('falha')):
            with self.assertRaises(RuntimeError):self.operate(order)
        order.refresh_from_db();self.assertEqual(order.status,'open');self.assertEqual(order.version,1);self.assertEqual(order.events.count(),1)

    def test_models_reject_edit_and_delete_without_service(self):
        order,_=self.create()
        with self.assertRaises(ValidationError):order.save()
        with self.assertRaises(ValidationError):order.delete()
        event=order.events.get()
        with self.assertRaises(ValidationError):event.save()
        with self.assertRaises(ValidationError):event.delete()

    def test_filters_overdue_and_invalid_input(self):
        order,_=self.create()
        response=self.client.get(self.endpoint()+'&overdue=1');self.assertEqual(response.data['count'],1)
        self.operate(order,'cancel',reason='Desistência')
        response=self.client.get(self.endpoint()+'&overdue=1');self.assertEqual(response.data['count'],0)
        for suffix in ['&status=invalid','&sale_id=abc','&sale_id=-1']:
            self.assertEqual(self.client.get(self.endpoint()+suffix).status_code,400)
        data={'request_id':str(uuid4()),'action':'create','sale_id':order.sale_id,'promised_on':'invalid'}
        self.assertEqual(self.client.post(self.endpoint(),data,format='json').status_code,400)

    def test_post_requires_csrf_with_session_auth(self):
        self.grant();sale=self.sale();client=APIClient(enforce_csrf_checks=True);client.force_login(self.user)
        response=client.post(self.endpoint(),{'request_id':str(uuid4()),'action':'create','sale_id':sale.pk,'promised_on':'2026-11-01'},format='json')
        self.assertEqual(response.status_code,403)

    def test_clinical_snapshot_requires_separate_permission(self):
        from organizations.test_prescriptions import PrescriptionAPITests
        PrescriptionAPITests.grant(self)
        response=self.client.post(f'/api/me/prescriptions/?store_id={self.store.pk}',{'request_id':str(uuid4()),'customer_id':self.customer.pk,'issued_on':'2026-10-01','od_sphere':'-1.25'},format='json')
        self.assertEqual(response.status_code,200,response.data)
        rx=response.data
        data=self.data();data['prescription_selection']={'prescription_id':rx['id'],'version':rx['version'],'expected_record_id':None}
        response=self.client.post(self.url,data,format='json');self.assertEqual(response.status_code,200,response.data)
        order,_=self.create(Sale.objects.get(pk=response.data['id']))
        self.assertEqual(self.client.get(self.endpoint(order)).data['prescription']['snapshot']['od_sphere'],'-1.25')
        self.user.user_permissions.remove(*Permission.objects.filter(content_type__app_label='organizations',codename='view_prescription'))
        for attr in ('_perm_cache','_user_perm_cache','_group_perm_cache'):
            if hasattr(self.user,attr):delattr(self.user,attr)
        response=self.client.get(self.endpoint(order))
        self.assertTrue(response.data['has_prescription']);self.assertIsNone(response.data['prescription'])
        self.assertNotIn('snapshot',self.client.get(self.endpoint()).data['results'][0])

    def test_other_authorized_store_cannot_read_or_change_order(self):
        from accounts.models import StoreMembership
        order,_=self.create()
        StoreMembership.objects.create(user=self.user,store=self.other,role=StoreMembership.Role.SELLER)
        self.assertEqual(self.client.get(self.endpoint(order,self.other)).status_code,404)
        response=self.client.post(self.endpoint(order,self.other),{'request_id':str(uuid4()),'action':'cancel','expected_version':1,'reason':'Tentativa'},format='json')
        self.assertEqual(response.status_code,404)
        self.assertEqual(self.client.get(self.endpoint(store=self.other)).data['count'],0)

    def test_foreign_request_id_cannot_be_replayed_by_other_user(self):
        order,data=self.create();self.grant(self.admin);self.client.force_authenticate(self.admin)
        self.assertEqual(self.client.post(self.endpoint(),data,format='json').status_code,403)
        self.assertEqual(order.events.count(),1)

    def test_edit_keeps_opening_snapshot_and_records_previous_details(self):
        order,_=self.create();snapshot=order.snapshot.copy()
        self.operate(order,'update',reason='Troca de laboratório',laboratory='Novo laboratório',notes='Conferir encaixe')
        order.refresh_from_db();self.assertEqual(order.snapshot,snapshot)
        self.assertEqual(order.events.get(version=1).snapshot['laboratory'],'Laboratório teste')
        self.assertEqual(order.events.get(version=2).snapshot['laboratory'],'Novo laboratório')
        order.snapshot={'forged':True}
        with self.assertRaises(ValidationError):order.save(_service=True)


from concurrent.futures import ThreadPoolExecutor
from datetime import date
from django.contrib.auth import get_user_model
from django.db import close_old_connections, connection
from django.test import TransactionTestCase
from unittest import skipUnless
from .work_order_services import operate_order


@skipUnless(connection.vendor == 'postgresql', 'Verificação de locks exige PostgreSQL.')
class ServiceOrderConcurrencyTests(TransactionTestCase):
    setUp = fixtures.PaymentCheckoutTests.setUp
    data = fixtures.PaymentCheckoutTests.data
    grant = ServiceOrderTests.grant
    sale = ServiceOrderTests.sale

    def test_simultaneous_retry_creates_only_one_order_and_event(self):
        self.grant();sale=self.sale()
        values={'request_id':uuid4(),'action':'create','promised_on':date(2026,11,1)}
        user_id=self.user.pk;store_id=self.store.pk
        def worker(_):
            close_old_connections()
            try:
                from organizations.models import Store
                result=operate_order(user=get_user_model().objects.get(pk=user_id),store=Store.objects.get(pk=store_id),sale_id=sale.pk,order_id=None,values=values,digest='same-payload')
                return result.pk
            finally:close_old_connections()
        with ThreadPoolExecutor(max_workers=2) as pool:
            ids=list(pool.map(worker,range(2)))
        self.assertEqual(ids[0],ids[1]);self.assertEqual(ServiceOrder.objects.count(),1);self.assertEqual(ServiceOrderEvent.objects.count(),1)
