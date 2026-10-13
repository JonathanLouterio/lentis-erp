from decimal import Decimal
from rest_framework import serializers
from .models import CashSession, CashPosting
from .cash_services import can_operate


class OpenCashSerializer(serializers.Serializer):
    account_id = serializers.IntegerField(min_value=1, max_value=9223372036854775807)
    amount = serializers.DecimalField(max_digits=12, decimal_places=2, min_value=Decimal('0'))
    note = serializers.CharField(max_length=255, required=False, default='', allow_blank=True)
    request_id = serializers.UUIDField()


class CashMoveSerializer(serializers.Serializer):
    kind = serializers.ChoiceField(choices=['supply', 'withdrawal'])
    amount = serializers.DecimalField(max_digits=12, decimal_places=2, min_value=Decimal('0.01'))
    reason = serializers.CharField(max_length=255)
    request_id = serializers.UUIDField()


class CloseCashSerializer(serializers.Serializer):
    counted_amount = serializers.DecimalField(max_digits=12, decimal_places=2, min_value=Decimal('0'))
    note = serializers.CharField(max_length=255, required=False, default='', allow_blank=True)
    request_id = serializers.UUIDField()


class CashSessionSerializer(serializers.ModelSerializer):
    account_name = serializers.CharField(source='account.name', read_only=True)
    owner_username = serializers.CharField(source='opened_by.username', read_only=True)
    closer_username = serializers.CharField(source='closed_by.username', read_only=True, allow_null=True)
    expected_cash = serializers.DecimalField(max_digits=28, decimal_places=2, read_only=True)
    difference = serializers.DecimalField(max_digits=28, decimal_places=2, read_only=True, allow_null=True)
    can_operate = serializers.SerializerMethodField()
    class Meta:
        model = CashSession
        fields = ['id', 'account', 'account_name', 'opened_by', 'owner_username', 'opened_at', 'opening_amount', 'opening_note', 'closed_at', 'closer_username', 'counted_amount', 'expected_cash', 'difference', 'closing_note', 'can_operate']
    def get_can_operate(self, obj):
        return obj.closed_at is None and can_operate(self.context['request'].user, obj)


class CashPostingSerializer(serializers.ModelSerializer):
    kind_label = serializers.CharField(source='get_kind_display', read_only=True)
    creator_username = serializers.CharField(source='created_by.username', read_only=True)
    sale_id = serializers.SerializerMethodField()
    class Meta:
        model = CashPosting
        fields = ['id', 'kind', 'kind_label', 'amount', 'reason', 'created_at', 'creator_username', 'financial_entry', 'sale_id']
    def get_sale_id(self, obj):
        return obj.financial_entry.receivable.payment.sale_id if obj.financial_entry_id else None
