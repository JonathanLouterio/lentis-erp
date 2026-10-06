from django.contrib.auth import get_user_model
from rest_framework import serializers

from organizations.models import Store


class AccessibleStoreSerializer(serializers.ModelSerializer):
    class Meta:
        model = Store
        fields = ("id", "code", "name")
        read_only_fields = fields


class CurrentUserSerializer(serializers.ModelSerializer):
    class Meta:
        model = get_user_model()
        fields = (
            "id",
            "username",
            "first_name",
            "last_name",
            "theme",
        )
        read_only_fields = fields


class UserPreferencesSerializer(serializers.ModelSerializer):
    class Meta:
        model = get_user_model()
        fields = ("theme",)