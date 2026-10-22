from decimal import Decimal
from zoneinfo import ZoneInfo
from django.shortcuts import get_object_or_404, render
from django.utils import timezone
from rest_framework.renderers import JSONRenderer, BrowsableAPIRenderer
from .models import Quote
from rest_framework.permissions import IsAuthenticated
from .quote_permissions import QuoteActionPermission
from .views import SalesBaseView


def money(value):
    return f'R$ {value:,.2f}'.replace(',', '@').replace('.', ',').replace('@', '.')


def quantity(value):
    return format(value, 'f').rstrip('0').rstrip('.').replace('.', ',') if '.' in format(value, 'f') else str(value)


class QuotePrintView(SalesBaseView):
    permission_classes=[IsAuthenticated,QuoteActionPermission]
    quote_actions={"GET":"print"}

    renderer_classes = [JSONRenderer, BrowsableAPIRenderer]

    def get(self, request, quote_id):
        store = self._selected_store()
        quote = get_object_or_404(Quote.objects.select_related('customer', 'store__company').prefetch_related('items'), pk=quote_id, store=store)
        items = list(quote.items.all())
        customer = quote.customer
        address = ''
        if customer:
            street = ', '.join(value for value in [customer.street, customer.address_number] if value)
            city = ' / '.join(value for value in [customer.city, customer.state] if value)
            address = ' - '.join(value for value in [street, customer.address_complement, customer.neighborhood, city, customer.zip_code] if value)
        context = {
            'quote': quote, 'store': store, 'customer': customer, 'address': address,
            'issued_at': timezone.localtime(quote.created_at, ZoneInfo('America/Sao_Paulo')),
            'rows': [{'name': item.product_name, 'code': item.product_code, 'quantity': quantity(item.quantity),
                      'price': money(item.unit_price), 'discount': money(item.discount_amount), 'total': money(item.total)} for item in items],
            'subtotal': money(quote.subtotal), 'item_discount': money(sum((item.discount_amount for item in items), Decimal('0'))),
            'discount': money(quote.discount_amount), 'total': money(quote.total),
        }
        response = render(request, 'sales/quote_print.html', context)
        response['Cache-Control'] = 'no-store, private'
        response['X-Content-Type-Options'] = 'nosniff'
        response['Referrer-Policy'] = 'no-referrer'
        response['X-Frame-Options'] = 'DENY'
        return response
