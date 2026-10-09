from decimal import Decimal

from rest_framework import serializers

from organizations.models import Customer, Product

from .models import Sale, SaleEvent, SaleItem


class SaleItemSerializer(serializers.ModelSerializer):
    subtotal = serializers.DecimalField(max_digits=28, decimal_places=2, read_only=True)
    total = serializers.DecimalField(max_digits=28, decimal_places=2, read_only=True)

    class Meta:
        model = SaleItem
        fields = ["id", "product", "product_code", "product_name", "quantity", "unit_price", "discount_amount", "subtotal", "total"]
        read_only_fields = fields


class SaleEventSerializer(serializers.ModelSerializer):
    event_label = serializers.CharField(source="get_event_type_display", read_only=True)
    creator_username = serializers.CharField(source="created_by.username", read_only=True)

    class Meta:
        model = SaleEvent
        fields = ["id", "event_type", "event_label", "created_by", "creator_username", "reason", "created_at"]
        read_only_fields = fields


class SaleSerializer(serializers.ModelSerializer):
    store_name = serializers.CharField(source="store.name", read_only=True)
    customer_name = serializers.CharField(source="customer.name", read_only=True, default=None)
    creator_username = serializers.CharField(source="created_by.username", read_only=True)
    status_label = serializers.CharField(source="get_status_display", read_only=True)
    items = SaleItemSerializer(many=True, read_only=True)
    events = SaleEventSerializer(many=True, read_only=True)
    subtotal = serializers.DecimalField(max_digits=28, decimal_places=2, read_only=True)
    discount_total = serializers.DecimalField(max_digits=28, decimal_places=2, read_only=True)
    total = serializers.DecimalField(max_digits=28, decimal_places=2, read_only=True)
    payments = serializers.SerializerMethodField()
    financial_status = serializers.SerializerMethodField()
    stock_warnings = serializers.SerializerMethodField()
    can_edit = serializers.SerializerMethodField()
    can_finalize = serializers.SerializerMethodField()
    can_cancel = serializers.SerializerMethodField()

    class Meta:
        model = Sale
        fields = [
            "id", "store", "store_name", "customer", "customer_name", "created_by", "creator_username",
            "status", "status_label", "notes", "created_at", "updated_at", "completed_at", "cancelled_at",
            "cancellation_reason", "items", "events", "subtotal", "discount_total", "total",
            "can_edit", "can_finalize", "can_cancel", "discount_amount", "payments", "financial_status", "stock_warnings",
        ]
        read_only_fields = fields

    def get_payments(self, sale):
        from .payment_serializers import SalePaymentSerializer
        return SalePaymentSerializer(sale.payments.all(), many=True, context=self.context).data

    def get_financial_status(self, sale):
        if sale.status == Sale.Status.DRAFT:
            return "planned" if sale.payments.exists() else "none"
        if sale.completed_at is None:
            return "none"
        return "recorded" if sale.payments.exists() or sale.total == 0 else "legacy"

    def get_stock_warnings(self, sale):
        # Os valores são da movimentação original, inclusive após uma reposição.
        links = sale.events.filter(
            event_type="completed", stock_movements__movement__balance_after__lt=0,
        ).values(
            "stock_movements__item__product_id", "stock_movements__item__product_code",
            "stock_movements__item__product_name", "stock_movements__movement__balance_before",
            "stock_movements__movement__balance_after",
        )
        return [{
            "product": row["stock_movements__item__product_id"],
            "product_code": row["stock_movements__item__product_code"],
            "product_name": row["stock_movements__item__product_name"],
            "balance_before": str(row["stock_movements__movement__balance_before"]),
            "balance_after": str(row["stock_movements__movement__balance_after"]),
        } for row in links]

    def get_can_edit(self, sale):
        return sale.status == Sale.Status.DRAFT

    def get_can_finalize(self, sale):
        return sale.status == Sale.Status.DRAFT and bool(sale.items.all())

    def get_can_cancel(self, sale):
        user = self.context["request"].user
        return sale.status == Sale.Status.DRAFT or (
            sale.status == Sale.Status.COMPLETED and (user.is_staff or user.is_superuser)
        )


class SaleDraftSerializer(serializers.Serializer):
    customer_id = serializers.IntegerField(required=False, allow_null=True, min_value=1, max_value=9223372036854775807)
    notes = serializers.CharField(required=False, allow_blank=True, default="", max_length=10000)

    def validate_customer_id(self, value):
        if value is None:
            return None
        customer = Customer.objects.filter(pk=value, store=self.context["store"], is_active=True).first()
        if customer is None:
            raise serializers.ValidationError("Selecione um cliente ativo da unidade da venda.")
        return customer


class SaleItemWriteSerializer(serializers.Serializer):
    product_id = serializers.IntegerField(min_value=1, max_value=9223372036854775807)
    quantity = serializers.DecimalField(max_digits=12, decimal_places=3, min_value=Decimal("0.001"), default=Decimal("1"))
    unit_price = serializers.DecimalField(max_digits=12, decimal_places=2, min_value=Decimal("0"), required=False)
    discount_amount = serializers.DecimalField(max_digits=12, decimal_places=2, min_value=Decimal("0"), default=Decimal("0"))

    def validate_product_id(self, value):
        product = Product.objects.filter(pk=value, store=self.context["store"], is_active=True).first()
        if product is None:
            raise serializers.ValidationError("Selecione um produto ativo da unidade da venda.")
        return product


class SaleCreateSerializer(SaleDraftSerializer):
    items = SaleItemWriteSerializer(many=True, required=False, default=list, max_length=200)


class SaleCancelSerializer(serializers.Serializer):
    reason = serializers.CharField(max_length=255, allow_blank=False)
