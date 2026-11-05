"""Lê arquivos limitados, orienta, remove metadados e produz dois JPEGs estáticos."""
from io import BytesIO
from threading import BoundedSemaphore
import warnings
from PIL import Image, ImageOps, UnidentifiedImageError
from rest_framework.exceptions import APIException, ValidationError

MAX_UPLOAD = 5 * 1024 * 1024
MAX_IMAGE = 1024 * 1024
MAX_THUMB = 96 * 1024
_slot = BoundedSemaphore(1)


class PhotoBusy(APIException):
    status_code = 429
    default_detail = 'Uma foto está sendo processada. Aguarde um momento e tente novamente.'


def encode(image, size, limit):
    image.thumbnail(size, Image.Resampling.LANCZOS)
    rgba = image.convert('RGBA')
    with Image.new('RGB', rgba.size, 'white') as clean:
        clean.paste(rgba, mask=rgba.getchannel('A'))
        for quality in (85, 75, 60):
            output = BytesIO()
            clean.save(output, 'JPEG', quality=quality, optimize=True)
            if len(output.getvalue()) <= limit:
                rgba.close()
                return output.getvalue()
    rgba.close()
    raise ValidationError('Não foi possível reduzir esta foto. Escolha outra imagem.')


def normalize_product_photo(upload):
    if upload.size > MAX_UPLOAD:
        raise ValidationError('Cada foto deve ter até 5 MB.')
    data = upload.read(MAX_UPLOAD + 1)
    if not data or len(data) > MAX_UPLOAD:
        raise ValidationError('Cada foto deve ter até 5 MB.')
    if not _slot.acquire(blocking=False):
        raise PhotoBusy()
    try:
        with warnings.catch_warnings():
            warnings.simplefilter('error', Image.DecompressionBombWarning)
            with Image.open(BytesIO(data), formats=('JPEG', 'PNG', 'WEBP')) as probe:
                if probe.width * probe.height > 16_000_000:
                    raise ValidationError('Cada foto deve ter no máximo 16 megapixels.')
                if getattr(probe, 'is_animated', False):
                    raise ValidationError('Escolha uma foto estática, sem animação.')
                probe.verify()
            with Image.open(BytesIO(data), formats=('JPEG', 'PNG', 'WEBP')) as source:
                source.load()
                ImageOps.exif_transpose(source, in_place=True)
                with source.copy() as full, source.copy() as thumb:
                    return {'image': encode(full, (1600, 1600), MAX_IMAGE),
                            'thumb': encode(thumb, (240, 240), MAX_THUMB)}
    except (UnidentifiedImageError, OSError, SyntaxError, ValueError, Image.DecompressionBombError, Image.DecompressionBombWarning) as exc:
        raise ValidationError('Envie uma imagem JPG, PNG ou WebP válida, sem animação.') from exc
    finally:
        _slot.release()
