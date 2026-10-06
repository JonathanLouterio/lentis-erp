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
            "name",
            "cpf",
            "birth_date",
            "phone",
            "email",
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
            raise serializers.ValidationError(
                "Informe o nome do cliente."
            )
        return value

    def validate_cpf(self, value):
        if not value:
            return None
        digits = "".join(char for char in value if char.isdigit())
        if len(digits) != 11:
            raise serializers.ValidationError(
                "Informe um CPF com 11 dígitos."
            )
        return digits
