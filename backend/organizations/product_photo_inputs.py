import json
from django.core.files.uploadhandler import FileUploadHandler, StopUpload
from rest_framework.exceptions import APIException, ValidationError
from rest_framework.parsers import JSONParser, MultiPartParser
from .product_images import MAX_UPLOAD


class PhotoUploadRejected(APIException):
    status_code = 413
    default_detail = 'Envie até três fotos, cada uma com até 5 MB, nas posições 1, 2 e 3.'


class ProductUploadLimit(FileUploadHandler):
    def __init__(self, request):
        super().__init__(request)
        self.seen = set()
        self.size = 0

    def reject(self):
        self.request._product_upload_rejected = True
        raise StopUpload(connection_reset=False)

    def new_file(self, field_name, *args, **kwargs):
        if field_name not in ('photo_1', 'photo_2', 'photo_3') or field_name in self.seen:
            self.reject()
        self.seen.add(field_name)
        self.size = 0
        return super().new_file(field_name, *args, **kwargs)

    def receive_data_chunk(self, raw_data, start):
        self.size += len(raw_data)
        if self.size > MAX_UPLOAD:
            self.reject()
        return raw_data

    def file_complete(self, file_size):
        return None


class ProductWriteMixin:
    parser_classes = [JSONParser, MultiPartParser]

    def initialize_request(self, request, *args, **kwargs):
        request.upload_handlers.insert(0, ProductUploadLimit(request))
        return super().initialize_request(request, *args, **kwargs)

    def get_serializer(self, *args, **kwargs):
        if 'data' in kwargs:
            self._selected_store()  # Nega unidade não autorizada antes de decodificar imagens.
            if getattr(self.request._request, '_product_upload_rejected', False):
                raise PhotoUploadRejected()
            if self.request.content_type.startswith('multipart/'):
                raw = kwargs['data']
                if set(raw) - {'data', 'photo_1', 'photo_2', 'photo_3'} or len(raw.getlist('data')) != 1:
                    raise ValidationError('Envie os dados JSON no campo data e até três fotos.')
                try:
                    kwargs['data'] = json.loads(raw['data'])
                except (ValueError, TypeError) as exc:
                    raise ValidationError('Os dados do produto não são JSON válido.') from exc
        return super().get_serializer(*args, **kwargs)


