from rest_framework import serializers

from organizations.models import Store


class AccessibleStoreSerializer(serializers.ModelSerializer):
    class Meta:
        model = Store
        fields = ("id", "code", "name")
        read_only_fields = fields