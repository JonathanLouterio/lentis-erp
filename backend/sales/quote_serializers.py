from decimal import Decimal
from rest_framework import serializers
from .models import Quote, QuoteItem, QuoteEvent
from .serializers import SaleCreateSerializer, SaleItemWriteSerializer


class QuoteWriteSerializer(SaleCreateSerializer):
    request_id = serializers.UUIDField()
    expected_version = serializers.IntegerField(min_value=1, max_value=2147483647, required=False)
    valid_until = serializers.DateField()
    discount_amount = serializers.DecimalField(max_digits=12, decimal_places=2, min_value=Decimal('0'), default=Decimal('0'))
    items = SaleItemWriteSerializer(many=True, max_length=200)
    def validate(self, values):
        ids = [item['product_id'].pk for item in values['items']]
        if len(ids) != len(set(ids)):
            raise serializers.ValidationError({'items': 'Cada produto deve aparecer uma vez; ajuste a quantidade.'})
        values.pop('request_id')
        return values


class QuoteActionSerializer(serializers.Serializer):
    request_id = serializers.UUIDField()
    expected_version = serializers.IntegerField(min_value=1, max_value=2147483647)
    reason = serializers.CharField(max_length=255, default='', allow_blank=True)
    def validate(self, values):
        values.pop('request_id')
        return values


class QuoteItemSerializer(serializers.ModelSerializer):
    subtotal = serializers.DecimalField(max_digits=28, decimal_places=2, read_only=True)
    total = serializers.DecimalField(max_digits=28, decimal_places=2, read_only=True)
    class Meta:
        model = QuoteItem
        fields = ['id','product','product_name','product_code','quantity','unit_price','discount_amount','subtotal','total']


class QuoteEventSerializer(serializers.ModelSerializer):
    creator_username = serializers.CharField(source='created_by.username', read_only=True)
    class Meta:
        model = QuoteEvent
        fields = ['id','action','creator_username','reason','created_at','version']


class QuoteSerializer(serializers.ModelSerializer):
    customer_name = serializers.CharField(source='customer.name', read_only=True, default=None)
    creator_username = serializers.CharField(source='created_by.username', read_only=True)
    status_label = serializers.CharField(source='get_status_display', read_only=True)
    is_expired = serializers.BooleanField(read_only=True)
    subtotal = serializers.DecimalField(max_digits=28, decimal_places=2, read_only=True)
    total = serializers.DecimalField(max_digits=28, decimal_places=2, read_only=True)
    items = QuoteItemSerializer(many=True, read_only=True)
    events = QuoteEventSerializer(many=True, read_only=True)
    class Meta:
        model = Quote
        fields = ['id','store','customer','customer_name','creator_username','status','status_label','is_expired','valid_until','notes','discount_amount','version','sale','created_at','updated_at','subtotal','total','items','events']
