from decimal import Decimal
from uuid import uuid4

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.test import TestCase
from rest_framework.test import APIClient

from accounts.models import StoreMembership
from organizations.models import Company, Store
from purchases.models import ExpenseTemplate, PayablePayment, PayablePlan


class ExpenseTemplateTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username='modelos')
        company = Company.objects.create(name='Ótica')
        self.store = Store.objects.create(company=company, code='01', name='Matriz')
        self.other = Store.objects.create(company=company, code='02', name='Filial')
        for store in [self.store, self.other]:
            StoreMembership.objects.create(user=self.user, store=store, role='manager')
        self.client = APIClient()
        self.client.force_authenticate(self.user)
        self.grant('view_payableplan', 'manage_expense_templates', 'add_operating_expense')

    def grant(self, *codes):
        self.user.user_permissions.add(*Permission.objects.filter(content_type__app_label='purchases', codename__in=codes))

    def revoke(self, code):
        self.user.user_permissions.remove(Permission.objects.get(content_type__app_label='purchases', codename=code))

    def data(self, **overrides):
        return {'name': 'Aluguel da matriz', 'category': 'rent', 'description': 'Aluguel da ótica',
                'payee': 'Imobiliária', 'suggested_amount': '950.00', 'due_day': 31, **overrides}

    def path(self, store=None, template_id=None):
        suffix = f'{template_id}/' if template_id is not None else ''
        return f'/api/me/payables/expense-templates/{suffix}?store_id={(store or self.store).pk}'

    def post(self, body, *, template_id=None, store=None, expected=201):
        response = self.client.post(self.path(store, template_id), body, format='json')
        self.assertEqual(response.status_code, expected, response.data)
        return response.data

    def rows(self, *, store=None, status='active', expected=200, **params):
        response = self.client.get('/api/me/payables/expense-templates/', {'store_id': (store or self.store).pk, 'status':status, **params})
        self.assertEqual(response.status_code, expected, response.data)
        return response.data.get('results')

    def test_creating_and_editing_a_template_does_not_create_or_change_financial_titles(self):
        row = self.post(self.data())
        self.assertFalse(PayablePlan.objects.exists())
        self.assertFalse(PayablePayment.objects.exists())
        self.assertEqual(self.rows(search='Aluguel')[0]['suggested_amount'], '950.00')
        response = self.client.post(f'/api/me/payables/expenses/?store_id={self.store.pk}', {
            'request_id':str(uuid4()), 'category':row['category'], 'description':row['description'], 'payee':row['payee'],
            'total':'960.00', 'first_due_date':'2026-11-29', 'installment_count':1,
        }, format='json')
        self.assertEqual(response.status_code, 200, response.data)
        changed = self.post(self.data(suggested_amount='990.00', due_day=10, version=row['version'], active=True),
                            template_id=row['id'], expected=200)
        self.assertEqual(changed['version'], row['version']+1)
        self.assertEqual(PayablePlan.objects.get().total, Decimal('960.00'))
        self.assertFalse(PayablePayment.objects.exists())

    def test_permissions_unit_scope_and_archive_restore(self):
        row = self.post(self.data(suggested_amount=None, due_day=None))
        self.assertEqual(self.rows(store=self.other), [])
        update = self.data(version=row['version'], active=False)
        self.post(update, template_id=row['id'], store=self.other, expected=404)
        archived = self.post(update, template_id=row['id'], expected=200)
        self.assertEqual(self.rows(), [])
        self.assertFalse(self.rows(status='all')[0]['active'])
        self.post(self.data(version=archived['version'], active=True), template_id=row['id'], expected=200)
        self.revoke('manage_expense_templates')
        self.assertEqual(self.rows()[0]['id'], row['id'])
        self.rows(status='all', expected=403)
        self.post(self.data(name='Internet'), expected=403)
        self.revoke('add_operating_expense')
        self.rows(expected=403)

    def test_unique_names_validation_and_stale_edits(self):
        row = self.post(self.data())
        self.post(self.data(name='  aluguel da MATRIZ '), expected=400)
        self.post(self.data(), store=self.other)
        self.post(self.data(name='Água', due_day=32), expected=400)
        self.post(self.data(name='Internet', suggested_amount='0.00'), expected=400)
        self.post(self.data(name='Aluguel revisto', version=row['version'], active=True), template_id=row['id'], expected=200)
        self.post(self.data(name='Dado antigo', version=row['version'], active=True), template_id=row['id'], expected=409)
        self.assertEqual(ExpenseTemplate.objects.get(pk=row['id']).name, 'Aluguel revisto')
