"""Perfil do próprio usuário. Identidade nunca é recebida do cliente."""
import json

from django.contrib.auth import get_user_model
from django.db import transaction
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from django.utils.crypto import constant_time_compare, salted_hmac
from django.utils.decorators import method_decorator
from django.views.decorators.cache import never_cache
from rest_framework import serializers
from rest_framework.authentication import SessionAuthentication
from rest_framework.exceptions import APIException, PermissionDenied, ValidationError
from rest_framework.parsers import JSONParser, MultiPartParser
from rest_framework.permissions import BasePermission
from rest_framework.response import Response
from rest_framework.views import APIView

from .profile_models import UserProfile
from .profile_images import normalize_avatar, MAX_UPLOAD_BYTES
from .profile_uploads import AvatarUploadLimit, AvatarUploadRejected
from .user_management_api import StrictSerializer

IDENTITY_FIELDS = ('first_name', 'last_name', 'email')
PERSONAL_FIELDS = ('phone', 'whatsapp', 'job_title', 'bio')


class ProfileConflict(APIException):
    status_code = 409
    default_detail = 'Seu perfil foi alterado em outra sessão. Feche a janela e atualize os dados antes de salvar.'


class ActiveProfileUser(BasePermission):
    def has_permission(self, request, view):
        return bool(request.user.is_authenticated and get_user_model().objects.filter(
            pk=request.user.pk, is_active=True).exists())


def profile_for(user):
    # A leitura dos dados pessoais não carrega a imagem em memória.
    return UserProfile.objects.defer('avatar').filter(user=user).first() or UserProfile(user=user)


def profile_version(user, profile):
    state = {field: getattr(user, field) for field in IDENTITY_FIELDS}
    state.update({field: getattr(profile, field) for field in PERSONAL_FIELDS})
    state.update(user_id=user.pk, username=user.username, revision=profile.revision,
                 avatar=profile.avatar_sha256, credential=user.password)
    return salted_hmac('lentis.personal-profile.version', json.dumps(state, sort_keys=True), algorithm='sha256').hexdigest()


def profile_output(user, profile):
    return {
        'id': user.pk, 'username': user.username,
        **{field: getattr(user, field) for field in IDENTITY_FIELDS},
        **{field: getattr(profile, field) for field in PERSONAL_FIELDS},
        'avatar_url': f'/api/me/profile/avatar/?v={profile.avatar_sha256}' if profile.avatar_sha256 else None,
        'version': profile_version(user, profile),
    }


class ProfileInput(StrictSerializer):
    version = serializers.CharField(min_length=64, max_length=64)
    first_name = serializers.CharField(max_length=150, allow_blank=True, required=False)
    last_name = serializers.CharField(max_length=150, allow_blank=True, required=False)
    email = serializers.EmailField(max_length=254, allow_blank=True, required=False)
    phone = serializers.CharField(max_length=20, allow_blank=True, required=False)
    whatsapp = serializers.CharField(max_length=20, allow_blank=True, required=False)
    job_title = serializers.CharField(max_length=80, allow_blank=True, required=False)
    bio = serializers.CharField(max_length=500, allow_blank=True, required=False)
    photo = serializers.FileField(required=False, allow_empty_file=False)
    remove_avatar = serializers.BooleanField(required=False, default=False)

    def validate_phone_number(self, value):
        if not value:
            return ''
        if any(char not in '+0123456789 ()-.' for char in value):
            raise ValidationError('Use somente números, DDD e DDI, com ou sem pontuação.')
        digits = ''.join(char for char in value if char in '0123456789')
        if not 10 <= len(digits) <= 15:
            raise ValidationError('Informe de 10 a 15 dígitos, incluindo DDD.')
        return digits

    def validate_phone(self, value):
        return self.validate_phone_number(value)

    def validate_whatsapp(self, value):
        return self.validate_phone_number(value)

    def validate(self, values):
        if values.get('photo') and values.get('remove_avatar'):
            raise ValidationError('Escolha entre enviar uma nova foto e remover a atual.')
        if 'photo' in values:
            values['normalized_avatar'] = normalize_avatar(values.pop('photo'))
        return values


@method_decorator(never_cache, name='dispatch')
class ProfileBaseView(APIView):
    authentication_classes = [SessionAuthentication]
    permission_classes = [ActiveProfileUser]

    def actor(self, request, *, lock=False):
        query = get_user_model().objects
        if lock:
            query = query.select_for_update()
        user = query.filter(pk=request.user.pk, is_active=True).first()
        if user is None:
            raise PermissionDenied('Sua conta não está disponível. Entre novamente.')
        return user

    def finalize_response(self, request, response, *args, **kwargs):
        response = super().finalize_response(request, response, *args, **kwargs)
        response['Cache-Control'] = 'no-store, private'
        response['X-Content-Type-Options'] = 'nosniff'
        return response


class MyProfileView(ProfileBaseView):
    parser_classes = [JSONParser, MultiPartParser]

    def initialize_request(self, request, *args, **kwargs):
        request.upload_handlers.insert(0, AvatarUploadLimit(request))
        return super().initialize_request(request, *args, **kwargs)

    def get(self, request):
        user = self.actor(request)
        return Response(profile_output(user, profile_for(user)))

    def patch(self, request):
        length = request.META.get('CONTENT_LENGTH', '')
        if length.isdigit() and int(length) > MAX_UPLOAD_BYTES + 64 * 1024:
            raise AvatarUploadRejected()
        data = request.data
        if getattr(request._request, '_avatar_upload_rejected', False):
            raise AvatarUploadRejected()
        payload = ProfileInput(data=data)
        payload.is_valid(raise_exception=True)
        values = dict(payload.validated_data)
        with transaction.atomic():
            # Mesmo lock usado pela gestão administrativa ao editar este usuário.
            user = self.actor(request, lock=True)
            profile = profile_for(user)
            if not constant_time_compare(values.pop('version'), profile_version(user, profile)):
                raise ProfileConflict()
            for field in IDENTITY_FIELDS:
                if field in values:
                    setattr(user, field, values[field])
            user.save(update_fields=[field for field in IDENTITY_FIELDS if field in values])
            for field in PERSONAL_FIELDS:
                if field in values:
                    setattr(profile, field, values[field])
            if 'normalized_avatar' in values:
                profile.avatar, profile.avatar_sha256 = values['normalized_avatar']
            elif values['remove_avatar']:
                profile.avatar, profile.avatar_sha256 = b'', ''
            profile.revision += 1
            profile.save()
            return Response(profile_output(user, profile))


class MyAvatarView(ProfileBaseView):
    def get(self, request):
        user = self.actor(request)
        profile = get_object_or_404(UserProfile.objects.only('avatar'), user=user)
        if not profile.avatar:
            return HttpResponse(status=404)
        response = HttpResponse(bytes(profile.avatar), content_type='image/jpeg')
        response['Content-Disposition'] = 'inline; filename="avatar.jpg"'
        response['Cross-Origin-Resource-Policy'] = 'same-origin'
        return response
