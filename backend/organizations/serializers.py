from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import serializers

from .models import Customer


class CustomerSerializer(serializers.ModelSerializer):
    store_name = serializers.CharField(source="store.name", read_only=True)

    class Meta:
        model = Customer
        fields = (
            "id",
            "store",
            "store_name",
            "person_type",
            "name",
            "trade_name",
            "cpf",
            "cnpj",
            "rg",
            "state_registration",
            "birth_date",
            "phone",
            "whatsapp",
            "email",
            "zip_code",
            "street",
            "address_number",
            "address_complement",
            "neighborhood",
            "city",
            "state",
            "notes",
            "is_active",
            "created_at",
            "updated_at",
        )
        read_only_fields = (
            "id",
            "store",
            "store_name",
            "created_at",
            "updated_at",
        )

    def validate_name(self, value):
        value = value.strip()
        if not value:
            raise serializers.ValidationError("Informe o nome do cliente.")
        return value

    def validate_state(self, value):
        return value.strip().upper()

    def validate(self, attrs):
        # A nova unidade e adicionada em perform_create(), depois desta etapa.
        # Portanto, a validacao completa do model acontece em create().
        if self.instance is None:
            return attrs

        instance = self.instance or Customer()
        for field, value in attrs.items():
            setattr(instance, field, value)

        try:
            instance.full_clean()
        except DjangoValidationError as exc:
            if hasattr(exc, "message_dict"):
                raise serializers.ValidationError(exc.message_dict) from exc
            raise serializers.ValidationError(exc.messages) from exc

        return attrs

    def create(self, validated_data):
        instance = Customer(**validated_data)
        instance.full_clean()
        instance.save()
        return instance

    def update(self, instance, validated_data):
        for field, value in validated_data.items():
            setattr(instance, field, value)
        instance.full_clean()
        instance.save()
        return instance
