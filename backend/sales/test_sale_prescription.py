from uuid import uuid4
from unittest.mock import patch
from django.contrib.auth.models import Permission
from django.core.exceptions import ValidationError
from django.test import TestCase
from rest_framework.test import APIClient
from . import test_payments as fixtures
from organizations import test_prescriptions as rx_fixtures
from organizations.models import Prescription, Customer, StockMovement
from .models import Sale, SalePrescription, FinancialEntry


class SalePrescriptionTests(TestCase):
    setUp=fixtures.PaymentCheckoutTests.setUp
    data=fixtures.PaymentCheckoutTests.data
    grant=rx_fixtures.PrescriptionAPITests.grant

    def rx(self):
        self.grant()
        response=self.client.post(f'/api/me/prescriptions/?store_id={self.store.pk}',{'request_id':str(uuid4()),'customer_id':self.customer.pk,'issued_on':'2026-10-01','od_sphere':'-1.25','oe_sphere':'0.00'},format='json')
        self.assertEqual(response.status_code,200,response.data)
        return response.data

    def payload(self,rx=None,sale=None,**overrides):
        data=self.data(action='draft')
        if sale:data['sale_id']=sale['id']
        if rx:data['prescription_selection']={'prescription_id':rx['id'],'version':rx['version'],'expected_record_id':sale['prescription']['id'] if sale and sale['prescription'] else None}
        data.update(overrides);return data

    def send(self,data,expected=200):
        response=self.client.post(self.url,data,format='json');self.assertEqual(response.status_code,expected,response.data);return response.data

    def history(self,sale,expected=200):
        response=self.client.get(f'/api/me/sales/{sale["id"]}/prescription-history/?store_id={self.store.pk}')
        self.assertEqual(response.status_code,expected,response.data);return response.data

    def test_attaches_snapshot_in_same_draft_without_stock_or_financial_effect(self):
        rx=self.rx();sale=self.send(self.payload(rx));record=SalePrescription.objects.get()
        self.assertEqual(record.snapshot['customer_name'],self.customer.name);self.assertEqual(record.source_version,1);self.assertEqual(record.snapshot['od_sphere'],'-1.25');self.assertEqual(record.snapshot['oe_sphere'],'0.00');self.assertIsNone(record.snapshot['pd'])
        self.assertNotIn('snapshot',sale['prescription'])
        self.assertEqual(self.history(sale)[0]['snapshot'],record.snapshot)
        self.assertEqual(Sale.objects.get().prescription_record,record)
        self.assertFalse(StockMovement.objects.exists());self.assertFalse(FinancialEntry.objects.exists())

    def test_source_correction_does_not_change_saved_copy_or_silently_refresh_it(self):
        rx=self.rx();sale=self.send(self.payload(rx))
        body=rx_fixtures.PrescriptionAPITests.data(self,expected_version=1,reason='Corrige transcrição',od_sphere='-2.00')
        response=self.client.put(f'/api/me/prescriptions/{rx["id"]}/?store_id={self.store.pk}',body,format='json');self.assertEqual(response.status_code,200,response.data)
        self.send(self.payload(sale=sale))
        self.assertEqual(SalePrescription.objects.count(),1);self.assertEqual(self.history(sale)[0]['snapshot']['od_sphere'],'-1.25')
        self.send(self.payload(response.data,sale))
        self.assertEqual(SalePrescription.objects.count(),2);self.assertEqual(self.history(sale)[0]['snapshot']['od_sphere'],'-2.00')

    def test_changed_or_archived_source_is_rejected_on_explicit_new_selection(self):
        rx=self.rx();Prescription.objects.filter(pk=rx['id']).update(version=2)
        self.send(self.payload(rx),expected=400)
        self.assertFalse(Sale.objects.exists());self.assertFalse(SalePrescription.objects.exists())
        Prescription.objects.filter(pk=rx['id']).update(version=1,is_active=False)
        self.send(self.payload(rx),expected=400)

    def test_source_from_other_customer_or_store_is_rejected(self):
        rx=self.rx();other=Customer.objects.create(store=self.store,name='Outro cliente')
        self.send(self.payload(rx,customer_id=other.pk),expected=400)
        self.send(self.payload(rx,customer_id=None),expected=400)
        Prescription.objects.filter(pk=rx['id']).update(store=self.other)
        self.send(self.payload(rx),expected=400)
        self.assertFalse(Sale.objects.exists())

    def test_view_permission_required_and_snapshot_not_exposed_to_other_roles(self):
        rx=self.rx();sale=self.send(self.payload(rx))
        self.client.force_authenticate(self.admin)
        response=self.client.get(f'/api/me/sales/{sale["id"]}/?store_id={self.store.pk}')
        self.assertEqual(response.status_code,200);self.assertIsNone(response.data['prescription']);self.assertFalse(response.data['can_view_prescription'])
        self.history(sale,expected=403)
        self.send(self.payload(rx),expected=403)
        self.send(self.payload(sale=sale))
        self.assertEqual(SalePrescription.objects.count(),1)

    def test_customer_cannot_change_without_explicit_authorized_removal(self):
        rx=self.rx();sale=self.send(self.payload(rx));other=Customer.objects.create(store=self.store,name='Outro cliente')
        self.send(self.payload(sale=sale,customer_id=other.pk),expected=400)
        removed=self.send(self.payload(sale=sale,customer_id=other.pk,prescription_selection={'prescription_id':None,'expected_record_id':sale['prescription']['id']}))
        self.assertIsNone(removed['prescription']);self.assertEqual(removed['customer'],other.pk)
        history=self.history(removed);self.assertEqual(len(history),2);self.assertEqual(history[0]['action'],'removed');self.assertEqual(history[1]['snapshot']['customer_id'],self.customer.pk)

    def test_stale_link_change_is_rejected_and_replay_does_not_duplicate_copy(self):
        rx=self.rx();data=self.payload(rx);sale=self.send(data);self.send(data)
        self.assertEqual(SalePrescription.objects.count(),1)
        self.send(self.payload(sale=sale,prescription_selection={'prescription_id':None,'expected_record_id':None}),expected=400)
        self.assertEqual(SalePrescription.objects.count(),1)

    def test_copy_survives_source_archive_and_sale_completion_and_cancel(self):
        rx=self.rx();sale=self.send(self.payload(rx));Prescription.objects.filter(pk=rx['id']).update(is_active=False)
        completed=self.send(self.payload(sale=sale,action='complete'))
        self.assertEqual(completed['status'],'completed');self.assertEqual(SalePrescription.objects.count(),1)
        self.client.force_authenticate(self.admin)
        result=self.client.post(f'/api/me/sales/{sale["id"]}/cancel/?store_id={self.store.pk}',{'reason':'Cancelamento de teste'},format='json')
        self.assertEqual(result.status_code,200,result.data)
        self.assertEqual(SalePrescription.objects.get().snapshot['od_sphere'],'-1.25')

    def test_direct_model_and_generic_api_cannot_replace_snapshot(self):
        rx=self.rx();sale=self.send(self.payload(rx));record=Sale.objects.get()
        record.prescription_record=None
        with self.assertRaises(ValidationError):record.save()
        self.client.patch(f'/api/me/sales/{sale["id"]}/?store_id={self.store.pk}',{'prescription_record':None,'prescription':{}},format='json')
        record.refresh_from_db();self.assertIsNotNone(record.prescription_record)
        copy=record.prescription_record
        with self.assertRaises(ValidationError):copy.save()
        with self.assertRaises(ValidationError):copy.delete()

    def test_finalized_sale_cannot_change_prescription(self):
        rx=self.rx();sale=self.send(self.payload(rx,action='complete'))
        self.send(self.payload(sale=sale,prescription_selection={'prescription_id':None,'expected_record_id':sale['prescription']['id']}),expected=400)
        self.assertEqual(SalePrescription.objects.count(),1)

    def test_checkout_failure_rolls_back_snapshot_and_sale(self):
        rx=self.rx()
        with patch('sales.payment_services.SaleItem.objects.create',side_effect=RuntimeError('Falha simulada')):
            with self.assertRaises(RuntimeError):self.send(self.payload(rx))
        self.assertFalse(Sale.objects.exists());self.assertFalse(SalePrescription.objects.exists())

    def test_anonymous_other_unit_and_missing_csrf_cannot_access_or_attach(self):
        rx=self.rx();sale=self.send(self.payload(rx))
        path=f'/api/me/sales/{sale["id"]}/prescription-history/'
        self.assertIn(self.client.get(path+f'?store_id={self.other.pk}').status_code,[400,403,404])
        client=APIClient(enforce_csrf_checks=True)
        self.assertEqual(client.get(path+f'?store_id={self.store.pk}').status_code,403)
        client.force_login(self.user);self.assertEqual(client.post(self.url,self.payload(rx),format='json').status_code,403)

    def test_history_response_is_private_and_no_change_to_copy_on_plain_save(self):
        rx=self.rx();sale=self.send(self.payload(rx));response=self.client.get(f'/api/me/sales/{sale["id"]}/prescription-history/?store_id={self.store.pk}')
        self.assertEqual(response['Cache-Control'],'no-store, private')
        self.send(self.payload(sale=sale));self.assertEqual(SalePrescription.objects.count(),1)
        with self.assertRaises(ValidationError):Sale.objects.get().delete()


from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from django.contrib.auth import get_user_model
from django.db import close_old_connections
from django.test import TransactionTestCase, skipUnlessDBFeature


class SalePrescriptionConcurrencyTests(TransactionTestCase):
    setUp=fixtures.PaymentCheckoutTests.setUp
    data=fixtures.PaymentCheckoutTests.data
    grant=rx_fixtures.PrescriptionAPITests.grant
    rx=SalePrescriptionTests.rx
    payload=SalePrescriptionTests.payload
    send=SalePrescriptionTests.send

    @skipUnlessDBFeature('has_select_for_update')
    def test_two_operators_cannot_overwrite_a_concurrent_selection(self):
        rx=self.rx();self.grant(self.admin);sale=self.send(self.payload())
        barrier=Barrier(2)
        def choose(user_id):
            close_old_connections()
            try:
                client=APIClient();client.force_authenticate(get_user_model().objects.get(pk=user_id))
                body=self.payload(rx,sale)
                barrier.wait(timeout=10)
                return client.post(self.url,body,format='json').status_code
            finally:close_old_connections()
        with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(choose,[self.user.pk,self.admin.pk]))
        self.assertEqual(sorted(results),[200,400]);self.assertEqual(SalePrescription.objects.count(),1)
