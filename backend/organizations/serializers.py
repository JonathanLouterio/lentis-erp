from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import serializers

from .models import Customer, Product


class ModelCleanMixin:
    @staticmethod
    def clean_instance(instance):
        try:
            instance.full_clean()
        except DjangoValidationError as exc:
            if hasattr(exc, "message_dict"):
                raise serializers.ValidationError(exc.message_dict) from exc
            raise serializers.ValidationError(exc.messages) from exc


class CustomerSerializer(ModelCleanMixin, serializers.ModelSerializer):
    store_name = serializers.CharField(source="store.name", read_only=True)

    class Meta:
        model = Customer
        fields = (
            "id", "store", "store_name", "person_type", "name", "trade_name",
            "cpf", "cnpj", "rg", "state_registration", "birth_date", "phone",
            "whatsapp", "email", "zip_code", "street", "address_number",
            "address_complement", "neighborhood", "city", "state", "notes",
            "is_active", "created_at", "updated_at",
        )
        read_only_fields = ("id", "store", "store_name", "created_at", "updated_at")

    def validate_name(self, value):
        value = value.strip()
        if not value:
            raise serializers.ValidationError("Informe o nome do cliente.")
        return value

    def validate_state(self, value):
        return value.strip().upper()

    def validate(self, attrs):
        if self.instance is None:
            return attrs
        instance = self.instance
        for field, value in attrs.items():
            setattr(instance, field, value)
        self.clean_instance(instance)
        return attrs

    def create(self, validated_data):
        instance = Customer(**validated_data)
        self.clean_instance(instance)
        instance.save()
        return instance

    def update(self, instance, validated_data):
        for field, value in validated_data.items():
            setattr(instance, field, value)
        self.clean_instance(instance)
        instance.save()
        return instance


class ProductSerializer(ModelCleanMixin, serializers.ModelSerializer):
    store_name = serializers.CharField(source="store.name", read_only=True)

    class Meta:
        model = Product
        fields = (
            "id", "store", "store_name", "internal_code", "barcode", "name",
            "brand", "category", "cost_price", "sale_price", "stock_quantity",
            "minimum_stock", "is_active", "created_at", "updated_at",
        )
        read_only_fields = ("id", "store", "store_name", "created_at", "updated_at")

    def validate_internal_code(self, value):
        value = value.strip()
        if not value:
            raise serializers.ValidationError("Informe o código interno.")
        return value

    def validate_name(self, value):
        value = value.strip()
        if not value:
            raise serializers.ValidationError("Informe a descrição do produto.")
        return value

    def validate(self, attrs):
        if self.instance is None:
            return attrs
        instance = self.instance
        for field, value in attrs.items():
            setattr(instance, field, value)
        self.clean_instance(instance)
        return attrs

    def create(self, validated_data):
        instance = Product(**validated_data)
        self.clean_instance(instance)
        instance.save()
        return instance

    def update(self, instance, validated_data):
        for field, value in validated_data.items():
            setattr(instance, field, value)
        self.clean_instance(instance)
        instance.save()
        return instance
