from django.contrib.auth import get_user_model
from rest_framework import serializers

from organizations.models import Store

from .models import StoreMembership


class AccessibleStoreSerializer(serializers.ModelSerializer):
    role = serializers.CharField(source="access_role", read_only=True)
    role_label = serializers.SerializerMethodField()

    class Meta:
        model = Store
        fields = ("id", "code", "name", "role", "role_label")
        read_only_fields = fields

    def get_role_label(self, obj):
        if obj.access_role == "superuser":
            return "Administrador do sistema"
        return StoreMembership.Role(obj.access_role).label


class CurrentUserSerializer(serializers.ModelSerializer):
    class Meta:
        model = get_user_model()
        fields = ("id", "username", "first_name", "last_name", "theme")
        read_only_fields = fields


class UserPreferencesSerializer(serializers.ModelSerializer):
    class Meta:
        model = get_user_model()
        fields = ("theme",)
