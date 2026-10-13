from datetime import timedelta
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient
from accounts.models import StoreMembership
from . import test_quotes as fixtures
from .models import Quote, Sale, FinancialEntry, QuoteEvent
from organizations.models import StockMovement


class QuotePrintTests(TestCase):
    setUp = fixtures.QuoteAPITests.setUp
    payload = fixtures.QuoteAPITests.payload
    write = fixtures.QuoteAPITests.write
    action = fixtures.QuoteAPITests.action
    accepted = fixtures.QuoteAPITests.accepted

    def print_quote(self, quote, store=None):
        return self.client.get(f'/api/me/quotes/{quote["id"]}/print/?store_id={(store or self.store).pk}', HTTP_ACCEPT='text/html')

    def test_print_shows_saved_totals_customer_store_and_does_not_write(self):
        quote = self.write()
        before = QuoteEvent.objects.count()
        response = self.print_quote(quote)
        self.assertEqual(response.status_code, 200)
        text = response.content.decode()
        for content in ['Cliente de parcelas','Matriz','R$ 1.270,00','R$ 1.300,00','R$ 20,00','R$ 10,00','RASCUNHO','lang="pt-BR"']:
            self.assertIn(content,text)
        self.assertEqual(response['Cache-Control'], 'no-store, private')
        self.assertEqual(QuoteEvent.objects.count(), before)
        self.assertFalse(Sale.objects.exists()); self.assertFalse(FinancialEntry.objects.exists()); self.assertFalse(StockMovement.objects.exists())

    def test_escapes_names_and_notes_instead_of_executing_markup(self):
        self.customer.name = '<script>alert(1)</script>'; self.customer.save()
        quote = self.write(self.payload(notes='<img src=x onerror=alert(2)>'))
        text = self.print_quote(quote).content.decode()
        self.assertIn('&lt;script&gt;', text); self.assertIn('&lt;img', text)
        self.assertNotIn('<script>alert(1)</script>', text); self.assertNotIn('<img src=x', text)

    def test_other_unit_anonymous_and_revoked_access_cannot_print(self):
        quote = self.write()
        self.assertIn(self.print_quote(quote, self.other).status_code, [400,403,404])
        self.client = APIClient()
        self.assertEqual(self.print_quote(quote).status_code,403)
        self.client.force_authenticate(self.user)
        StoreMembership.objects.filter(user=self.user).update(is_active=False)
        self.assertIn(self.print_quote(quote).status_code,[400,403])

    def test_expired_and_recused_labels_are_explicit(self):
        quote = self.write(self.payload(valid_until=str(timezone.localdate()-timedelta(days=2))))
        self.assertIn('VALIDADE VENCIDA',self.print_quote(quote).content.decode())
        rejected = self.action(quote,'reject',reason='Sem interesse')
        self.assertIn('ORÇAMENTO RECUSADO',self.print_quote(rejected).content.decode())

    def test_converted_document_does_not_claim_payment_received(self):
        quote = self.action(self.accepted(),'convert')
        text = self.print_quote(quote).content.decode()
        self.assertIn(f'venda #{quote["sale"]}',text)
        self.assertIn('Não é documento fiscal nem comprovante de pagamento.',text)
        self.assertEqual(Sale.objects.get().status,'draft')

    def test_print_only_accepts_read_requests(self):
        quote = self.write()
        path=f'/api/me/quotes/{quote["id"]}/print/?store_id={self.store.pk}'
        self.assertEqual(self.client.post(path,{},format='json').status_code,405)
