from decimal import Decimal
from rest_framework import serializers
from .models import FinancialAccount, FinancialEntry, PaymentMethod, Receivable, SalePayment
from .serializers import SaleCreateSerializer


class PaymentWriteSerializer(serializers.Serializer):
    method_id = serializers.IntegerField(min_value=1, max_value=9223372036854775807)
    account_id = serializers.IntegerField(min_value=1, max_value=9223372036854775807)
    amount = serializers.DecimalField(max_digits=18, decimal_places=2, min_value=Decimal('0.01'))
    installment_count = serializers.IntegerField(min_value=1, max_value=12, default=1)
    first_due_date = serializers.DateField()
    confirmed = serializers.BooleanField(default=False)

    def validate_method_id(self, value):
        method = PaymentMethod.objects.filter(pk=value, store=self.context['store'], is_active=True).first()
        if method is None:
            raise serializers.ValidationError('Selecione uma forma ativa desta unidade.')
        return method

    def validate_account_id(self, value):
        account = FinancialAccount.objects.filter(pk=value, store=self.context['store'], is_active=True).first()
        if account is None:
            raise serializers.ValidationError('Selecione uma conta ativa desta unidade.')
        return account


class CheckoutSerializer(SaleCreateSerializer):
    sale_id = serializers.IntegerField(required=False, allow_null=True, min_value=1, max_value=9223372036854775807)
    action = serializers.ChoiceField(choices=['draft', 'complete'])
    discount_amount = serializers.DecimalField(max_digits=12, decimal_places=2, min_value=Decimal('0'), default=Decimal('0'))
    payments = PaymentWriteSerializer(many=True, max_length=20, required=False, default=list)

    def validate(self, values):
        products = [item['product_id'].pk for item in values['items']]
        if len(products) != len(set(products)):
            raise serializers.ValidationError({'items': 'Cada produto deve aparecer uma vez; ajuste a quantidade do item.'})
        if values['action'] == 'complete' and not values['items']:
            raise serializers.ValidationError({'items': 'Adicione um produto à venda.'})
        return values


class ReceiptWriteSerializer(serializers.Serializer):
    method_id = serializers.IntegerField(min_value=1, max_value=9223372036854775807)
    account_id = serializers.IntegerField(min_value=1, max_value=9223372036854775807)
    amount = serializers.DecimalField(max_digits=18, decimal_places=2, min_value=Decimal("0.01"))
    request_id = serializers.UUIDField()
    validate_method_id = PaymentWriteSerializer.validate_method_id
    validate_account_id = PaymentWriteSerializer.validate_account_id


class AccountSerializer(serializers.ModelSerializer):
    balance = serializers.DecimalField(max_digits=28, decimal_places=2, read_only=True)
    class Meta:
        model = FinancialAccount
        fields = ['id', 'name', 'code', 'balance']


class MethodSerializer(serializers.ModelSerializer):
    class Meta:
        model = PaymentMethod
        fields = ['id', 'name', 'kind', 'code']


class EntrySerializer(serializers.ModelSerializer):
    account_name = serializers.CharField(source='account.name', read_only=True)
    method_name = serializers.CharField(source='method.name', read_only=True)
    creator_username = serializers.CharField(source='created_by.username', read_only=True)
    class Meta:
        model = FinancialEntry
        fields = ['id', 'account', 'account_name', 'method_name', 'amount', 'created_at', 'creator_username', 'reason', 'reversal_of']


class ReceivableSerializer(serializers.ModelSerializer):
    sale_id = serializers.IntegerField(source='payment.sale_id', read_only=True)
    method_name = serializers.CharField(source='payment.method_name', read_only=True)
    account_name = serializers.CharField(source='payment.account.name', read_only=True)
    installment_count = serializers.IntegerField(source='payment.installment_count', read_only=True)
    paid_amount = serializers.DecimalField(max_digits=18, decimal_places=2, read_only=True)
    remaining_amount = serializers.DecimalField(max_digits=18, decimal_places=2, read_only=True)
    status = serializers.CharField(read_only=True)
    can_receive = serializers.SerializerMethodField()
    entries = EntrySerializer(many=True, read_only=True)
    class Meta:
        model = Receivable
        fields = ['id', 'sale_id', 'number', 'installment_count', 'due_date', 'amount', 'paid_amount', 'remaining_amount', 'status', 'debtor', 'customer_name', 'method_name', 'account_name', 'can_receive', 'entries']

    def get_can_receive(self, obj):
        user = self.context['request'].user
        return (user.is_staff or user.is_superuser) and obj.status in ('pending', 'partial')


class SalePaymentSerializer(serializers.ModelSerializer):
    account_name = serializers.CharField(source='account.name', read_only=True)
    installments = ReceivableSerializer(many=True, read_only=True)
    class Meta:
        model = SalePayment
        fields = ['id', 'method', 'account', 'method_name', 'account_name', 'kind', 'amount', 'installment_count', 'first_due_date', 'confirmed', 'installments']
