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


class QuoteFollowupSerializer(QuoteActionSerializer):
    kind = serializers.ChoiceField(choices=('contact', 'schedule'))
    next_contact_on = serializers.DateField(allow_null=True)

    def validate(self, values):
        values = super().validate(values)
        if values['kind'] == 'schedule' and values['next_contact_on'] is None:
            raise serializers.ValidationError({'next_contact_on': 'Informe a data do retorno.'})
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
        fields = ['id','action','creator_username','reason','created_at','version','next_contact_on']


class QuoteSerializer(serializers.ModelSerializer):
    actions=serializers.SerializerMethodField()
    last_contact=serializers.SerializerMethodField()
    next_contact_on=serializers.SerializerMethodField()

    def get_last_contact(self,obj):
        for event in reversed(list(obj.events.all())):
            if event.action == 'updated':
                break
            if event.action == 'contact':
                return {'created_at': event.created_at, 'creator_username': event.created_by.username}
        return None

    def get_next_contact_on(self,obj):
        return obj.next_contact_on if obj.can_followup else None

    def get_actions(self,obj):
        from organizations.access_permissions import fresh_actor
        from .quote_permissions import available_quote_actions
        request=self.context.get('request')
        return available_quote_actions(obj,fresh_actor(request) if request else None)

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
        fields = ['id','store','customer','customer_name','creator_username','status','status_label','is_expired','valid_until','notes','discount_amount','version','sale','created_at','updated_at','subtotal','total','items','events','actions','last_contact','next_contact_on']
