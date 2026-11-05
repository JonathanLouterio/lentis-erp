"""R2 via S3, sem URL pública; disco local é permitido somente em desenvolvimento."""
import logging
import os
import re
from pathlib import Path
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from rest_framework.exceptions import APIException
from .product_images import MAX_IMAGE, MAX_THUMB

logger = logging.getLogger(__name__)


def log_photo_storage_error(operation, exc):
    # Nunca inclua a mensagem, o traceback, a chave do objeto ou a URL do SDK.
    response = getattr(exc, 'response', None)
    details = response.get('Error') if isinstance(response, dict) else None
    code = details.get('Code') if isinstance(details, dict) else None
    safe_code = code if isinstance(code, str) and re.fullmatch(r'[A-Za-z0-9_-]{1,64}', code) else '-'
    logger.warning('Falha no armazenamento de foto: operacao=%s tipo=%s codigo=%s',
                   operation, type(exc).__name__, safe_code)


class PhotoStorageUnavailable(APIException):
    status_code = 503
    default_detail = 'O armazenamento de fotos está indisponível. Os dados não foram alterados. Tente novamente ou solicite a configuração ao administrador.'


def setting(name, default=''):
    return getattr(settings, name, os.getenv(name, default))


def storage_kind():
    kind = setting('PRODUCT_PHOTO_STORAGE', 'r2')
    if kind not in ('local', 'r2') or (kind == 'local' and not settings.DEBUG):
        raise ImproperlyConfigured('Fotos em produção exigem PRODUCT_PHOTO_STORAGE=r2.')
    return kind


def r2_client():
    import boto3
    from botocore.config import Config
    endpoint = setting('LENTIS_R2_ENDPOINT')
    bucket = setting('LENTIS_R2_BUCKET')
    key, secret = setting('LENTIS_R2_ACCESS_KEY_ID'), setting('LENTIS_R2_SECRET_ACCESS_KEY')
    if not (re.fullmatch(r'https://[a-f0-9]{32}(?:\.(?:eu|fedramp))?\.r2\.cloudflarestorage\.com', endpoint)
            and re.fullmatch(r'[a-z0-9][a-z0-9.-]{1,61}[a-z0-9]', bucket) and key and secret):
        raise ImproperlyConfigured('Configure as quatro variáveis LENTIS_R2_* para um bucket privado do Lentis.')
    return boto3.client('s3', endpoint_url=endpoint, region_name='auto',
        aws_access_key_id=key, aws_secret_access_key=secret,
        config=Config(signature_version='s3v4', connect_timeout=4, read_timeout=10,
            retries={'total_max_attempts': 2, 'mode': 'standard'},
            request_checksum_calculation='when_required', response_checksum_validation='when_required'))


class PhotoStorage:
    def __init__(self, kind=None):
        self.kind = kind or storage_kind()
        if self.kind == 'local':
            if not settings.DEBUG:
                raise ImproperlyConfigured('Disco local não é aceito em produção.')
            self.root = Path(setting('PRODUCT_PHOTO_LOCAL_ROOT', settings.BASE_DIR.parent / 'media' / 'product-photos'))
        elif self.kind == 'r2':
            self.client = r2_client()
            self.bucket = setting('LENTIS_R2_BUCKET')
        else:
            raise ImproperlyConfigured('Armazenamento de fotos inválido.')

    def put(self, key, data):
        if self.kind == 'r2':
            self.client.put_object(Bucket=self.bucket, Key=key, Body=data,
                ContentType='image/jpeg', CacheControl='private, no-store')
        else:
            path = self.root / key
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)

    def get(self, key, variant):
        limit = MAX_THUMB if variant == 'thumb' else MAX_IMAGE
        if self.kind == 'r2':
            result = self.client.get_object(Bucket=self.bucket, Key=key)
            stream = result['Body']
            try:
                data = stream.read(limit + 1)
            finally:
                stream.close()
        else:
            with (self.root / key).open('rb') as stream:
                data = stream.read(limit + 1)
        if not data or len(data) > limit:
            raise ValueError('Objeto de imagem inválido.')
        return data

    def delete(self, key):
        if self.kind == 'r2':
            self.client.delete_object(Bucket=self.bucket, Key=key)
        else:
            (self.root / key).unlink(missing_ok=True)
