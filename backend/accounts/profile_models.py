"""Dados pessoais e avatar privado, separados das permissões e da autenticação."""
from django.conf import settings
from django.db import models


class UserProfile(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
                                related_name='personal_profile', primary_key=True)
    phone = models.CharField('Telefone', max_length=20, blank=True)
    whatsapp = models.CharField('WhatsApp', max_length=20, blank=True)
    job_title = models.CharField('Cargo / apresentação', max_length=80, blank=True)
    bio = models.CharField('Sobre mim', max_length=500, blank=True)
    revision = models.PositiveBigIntegerField(default=1, editable=False)
    # Avatar JPEG de 256x256, até 96 KiB. Não armazena o arquivo original.
    avatar = models.BinaryField(default=bytes, blank=True, editable=False)
    avatar_sha256 = models.CharField(max_length=64, blank=True, editable=False)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Perfil pessoal'
        verbose_name_plural = 'Perfis pessoais'
        default_permissions = ()
