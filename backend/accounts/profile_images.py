"""Decodificação limitada e regravação da foto; nunca publica bytes originais."""
from hashlib import sha256
from io import BytesIO
from threading import BoundedSemaphore
import warnings

from PIL import Image, ImageOps, UnidentifiedImageError
from rest_framework.exceptions import APIException, ValidationError

MAX_UPLOAD_BYTES = 5 * 1024 * 1024
MAX_AVATAR_BYTES = 96 * 1024
MAX_PIXELS = 16_000_000
ALLOWED_FORMATS = ('JPEG', 'PNG', 'WEBP')
_decode_slot = BoundedSemaphore(1)


class AvatarBusy(APIException):
    status_code = 429
    default_detail = 'Outro envio de foto está sendo processado. Aguarde um momento e tente novamente.'


def normalize_avatar(upload):
    if upload.size > MAX_UPLOAD_BYTES:
        raise ValidationError('Escolha uma foto de até 5 MB.')
    data = upload.read(MAX_UPLOAD_BYTES + 1)
    if not data or len(data) > MAX_UPLOAD_BYTES:
        raise ValidationError('Escolha uma foto de até 5 MB.')
    if not _decode_slot.acquire(blocking=False):
        raise AvatarBusy()
    try:
        with warnings.catch_warnings():
            warnings.simplefilter('error', Image.DecompressionBombWarning)
            with Image.open(BytesIO(data), formats=ALLOWED_FORMATS) as probe:
                if probe.width * probe.height > MAX_PIXELS:
                    raise ValidationError('A foto deve ter no máximo 16 megapixels. Reduza a resolução e tente novamente.')
                if getattr(probe, 'is_animated', False):
                    raise ValidationError('Escolha uma foto estática, sem animação.')
                probe.verify()
            with Image.open(BytesIO(data), formats=ALLOWED_FORMATS) as source:
                source.load()
                ImageOps.exif_transpose(source, in_place=True)
                with ImageOps.fit(source, (256, 256), method=Image.Resampling.LANCZOS) as resized:
                    rgba = resized.convert('RGBA')
                    clean = Image.new('RGB', (256, 256), 'white')
                    clean.paste(rgba, mask=rgba.getchannel('A'))
                    output = BytesIO()
                    clean.save(output, format='JPEG', quality=85, optimize=True)
                    rgba.close(); clean.close()
        encoded = output.getvalue()
        if len(encoded) > MAX_AVATAR_BYTES:
            raise ValidationError('Não foi possível reduzir a foto. Escolha outra imagem.')
        return encoded, sha256(encoded).hexdigest()
    except (UnidentifiedImageError, OSError, SyntaxError, ValueError, Image.DecompressionBombError, Image.DecompressionBombWarning) as exc:
        raise ValidationError('Envie uma imagem JPG, PNG ou WebP válida, sem animação.') from exc
    finally:
        _decode_slot.release()
