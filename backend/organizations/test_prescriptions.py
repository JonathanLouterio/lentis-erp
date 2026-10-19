from unittest.mock import patch
from uuid import uuid4
from django.contrib.auth.models import Permission
from django.test import TestCase
from rest_framework.test import APIClient
from sales import test_payments as fixtures
from .models import Customer, Prescription, PrescriptionRevision, PrescriptionOperation, StockMovement


class PrescriptionAPITests(TestCase):
    setUp = fixtures.PaymentCheckoutTests.setUp

    def grant(self, user=None, *codes):
        user = user or self.user
        codes = codes or ('view_prescription','add_prescription','change_prescription')
        user.user_permissions.add(*Permission.objects.filter(content_type__app_label='organizations',codename__in=codes))
        for attr in ('_perm_cache','_user_perm_cache','_group_perm_cache'):
            if hasattr(user,attr):delattr(user,attr)

    def data(self, **overrides):
        values={'request_id':str(uuid4()),'customer_id':self.customer.pk,'issued_on':'2026-10-01','prescriber_name':'Dr. Teste','prescriber_registration':'Registro informado','od_sphere':'-1.25','od_cylinder':'-0.50','od_axis':90,'oe_sphere':'0.00','pd':'62.50','notes':'Transcrição de teste'}
        values.update(overrides);return values

    def write(self,data=None,record=None,expected=200):
        suffix=f'{record["id"]}/' if record else ''
        response=(self.client.put if record else self.client.post)(f'/api/me/prescriptions/{suffix}?store_id={self.store.pk}',data or self.data(),format='json')
        self.assertEqual(response.status_code,expected,response.data)
        return response.data

    def archive(self,record,**overrides):
        data={'request_id':str(uuid4()),'expected_version':record['version'],'reason':'Cadastro duplicado'};data.update(overrides)
        return self.client.post(f'/api/me/prescriptions/{record["id"]}/archive/?store_id={self.store.pk}',data,format='json')

    def test_permission_required_even_for_staff(self):
        self.write(expected=403)
        self.client.force_authenticate(self.admin);self.write(expected=403)
        self.assertFalse(Prescription.objects.exists())

    def test_blank_is_distinct_from_zero_and_negative_values_are_preserved(self):
        self.grant();record=self.write()
        self.assertEqual(record['od_sphere'],'-1.25');self.assertEqual(record['oe_sphere'],'0.00');self.assertIsNone(record['oe_cylinder'])
        self.assertEqual(record['pd'],'62.50');self.assertFalse(StockMovement.objects.exists())

    def test_correction_preserves_both_versions_and_author(self):
        self.grant();record=self.write()
        new=self.write(self.data(expected_version=record['version'],od_sphere='-1.50',reason='Corrige digitação'),record)
        self.assertEqual(new['version'],2)
        revisions=list(PrescriptionRevision.objects.order_by('version'))
        self.assertEqual(revisions[0].snapshot['od_sphere'],'-1.25');self.assertEqual(revisions[1].snapshot['od_sphere'],'-1.50')
        self.assertEqual(revisions[1].created_by,self.user)

    def test_stale_edit_and_missing_reason_do_not_change_data(self):
        self.grant();record=self.write()
        self.write(self.data(expected_version=1),record,expected=400)
        self.write(self.data(expected_version=1,reason='Correção'),record)
        self.write(self.data(expected_version=1,reason='Conflito',od_sphere='-8'),record,expected=400)
        self.assertEqual(Prescription.objects.get().version,2)
        self.assertEqual(PrescriptionRevision.objects.count(),2)

    def test_same_operation_is_replayed_and_changed_body_rejected(self):
        self.grant();data=self.data();one=self.write(data);two=self.write(data)
        self.assertEqual(one['id'],two['id']);self.assertEqual(PrescriptionRevision.objects.count(),1)
        data['notes']='Outro';self.write(data,expected=400)

    def test_cross_unit_customer_and_transfer_are_rejected(self):
        self.grant();other_customer=Customer.objects.create(store=self.other,name='Outra unidade')
        self.write(self.data(customer_id=other_customer.pk),expected=400)
        record=self.write();same_store=Customer.objects.create(store=self.store,name='Outro cliente')
        self.write(self.data(customer_id=same_store.pk,expected_version=1,reason='Troca'),record,expected=400)
        self.assertEqual(Prescription.objects.get().customer,self.customer)

    def test_invalid_axis_distances_and_values_are_rejected(self):
        self.grant()
        for invalid in ({'od_axis':181},{'od_axis':-1},{'od_axis':None},{'od_axis':90.5},{'pd':'0'},{'pd':'-2'},{'od_sphere':'NaN'},{'od_sphere':'1.255'},{'od_cylinder':None}):
            self.write(self.data(**invalid),expected=400)
        self.assertFalse(Prescription.objects.exists())

    def test_no_eye_values_is_rejected_but_single_eye_zero_is_valid(self):
        self.grant();self.write(self.data(od_sphere=None,od_cylinder=None,od_axis=None,oe_sphere=None),expected=400)
        self.write(self.data(od_sphere=None,od_cylinder=None,od_axis=None,oe_sphere='0.00'))

    def test_archive_keeps_history_and_blocks_further_edits(self):
        self.grant();record=self.write()
        response=self.archive(record);self.assertEqual(response.status_code,200,response.data)
        self.assertFalse(response.data['is_active']);self.assertEqual(PrescriptionRevision.objects.count(),2)
        self.write(self.data(expected_version=2,reason='Altera'),response.data,expected=400)
        self.assertEqual(self.archive(record).status_code,400)
        self.assertEqual(self.client.delete(f'/api/me/prescriptions/{record["id"]}/?store_id={self.store.pk}').status_code,405)

    def test_view_permission_does_not_allow_corrections(self):
        self.grant();record=self.write();self.grant(self.admin,'view_prescription');self.client.force_authenticate(self.admin)
        path=f'/api/me/prescriptions/{record["id"]}/?store_id={self.store.pk}'
        self.assertEqual(self.client.get(path).status_code,200)
        self.write(self.data(expected_version=1,reason='Altera'),record,expected=403)
        self.assertEqual(self.archive(record).status_code,403)

    def test_read_scope_and_revocation_apply_to_detail_and_history(self):
        self.grant();record=self.write()
        path=f'/api/me/prescriptions/{record["id"]}/'
        self.assertIn(self.client.get(f'{path}?store_id={self.other.pk}').status_code,[400,403,404])
        from accounts.models import StoreMembership
        StoreMembership.objects.filter(user=self.user).update(is_active=False)
        self.assertIn(self.client.get(f'{path}?store_id={self.store.pk}').status_code,[400,403])

    def test_anonymous_and_missing_csrf_are_denied(self):
        self.grant();client=APIClient(enforce_csrf_checks=True)
        path=f'/api/me/prescriptions/?store_id={self.store.pk}'
        self.assertEqual(client.get(path).status_code,403)
        client.force_login(self.user);self.assertEqual(client.post(path,self.data(),format='json').status_code,403)
        self.assertFalse(Prescription.objects.exists())

    def test_forged_store_author_and_version_do_not_override_server(self):
        self.grant();record=self.write(self.data(store=self.other.pk,created_by=self.admin.pk,version=55,is_active=False))
        self.assertEqual(record['version'],1);self.assertEqual(record['store'],self.store.pk);self.assertTrue(record['is_active'])
        self.assertEqual(Prescription.objects.get().created_by,self.user)

    def test_history_write_failure_rolls_back_entire_operation(self):
        self.grant()
        with patch('organizations.prescription_api.PrescriptionRevision.objects.create',side_effect=RuntimeError('Falha simulada')):
            with self.assertRaises(RuntimeError):self.write()
        self.assertFalse(Prescription.objects.exists());self.assertFalse(PrescriptionOperation.objects.exists())

    def test_history_is_immutable_and_reads_are_not_cached(self):
        self.grant();record=self.write();revision=PrescriptionRevision.objects.get()
        from django.core.exceptions import ValidationError
        with self.assertRaises(ValidationError):revision.save()
        with self.assertRaises(ValidationError):revision.delete()
        response=self.client.get(f'/api/me/prescriptions/{record["id"]}/?store_id={self.store.pk}')
        self.assertEqual(response['Cache-Control'],'no-store, private');self.assertEqual(len(response.data['revisions']),1)

    def test_filter_archived_and_customer(self):
        self.grant();first=self.write();self.archive(first);self.write()
        base=f'/api/me/prescriptions/?store_id={self.store.pk}'
        self.assertEqual(self.client.get(base).data['count'],1)
        self.assertEqual(self.client.get(base+'&status=archived').data['count'],1)
        self.assertEqual(self.client.get(base+'&status=all').data['count'],2)
        self.assertEqual(self.client.get(base+'&customer_id=999999').data['count'],0)
        self.assertEqual(self.client.get(base+'&customer_id=abc').status_code,400)


from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from django.db import close_old_connections
from django.contrib.auth import get_user_model
from django.test import TransactionTestCase, skipUnlessDBFeature


class PrescriptionConcurrencyTests(TransactionTestCase):
    setUp = fixtures.PaymentCheckoutTests.setUp
    grant = PrescriptionAPITests.grant
    data = PrescriptionAPITests.data
    write = PrescriptionAPITests.write

    @skipUnlessDBFeature('has_select_for_update')
    def test_two_corrections_with_same_version_only_one_is_applied(self):
        self.grant();self.grant(self.admin);record=self.write()
        barrier=Barrier(2)
        def correct(user_id):
            close_old_connections()
            try:
                client=APIClient();client.force_authenticate(get_user_model().objects.get(pk=user_id))
                body=self.data(expected_version=1,reason='Conferência concorrente',od_sphere='-2.00')
                barrier.wait(timeout=10)
                return client.put(f'/api/me/prescriptions/{record["id"]}/?store_id={self.store.pk}',body,format='json').status_code
            finally:close_old_connections()
        with ThreadPoolExecutor(max_workers=2) as pool:
            results=list(pool.map(correct,[self.user.pk,self.admin.pk]))
        self.assertEqual(sorted(results),[200,400])
        self.assertEqual(Prescription.objects.get().version,2)
        self.assertEqual(PrescriptionRevision.objects.count(),2)
