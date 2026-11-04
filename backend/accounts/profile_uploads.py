"""Limita o total de bytes e de arquivos antes de armazenar o upload temporário."""
from django.core.files.uploadhandler import FileUploadHandler, StopUpload
from rest_framework.exceptions import APIException
from .profile_images import MAX_UPLOAD_BYTES


class AvatarUploadRejected(APIException):
    status_code = 413
    default_detail = 'Envie uma única foto de até 5 MB no campo photo.'


class AvatarUploadLimit(FileUploadHandler):
    def __init__(self, request):
        super().__init__(request)
        self.total = 0
        self.files = 0

    def new_file(self, field_name, *args, **kwargs):
        self.files += 1
        if field_name != 'photo' or self.files > 1:
            self.request._avatar_upload_rejected = True
            raise StopUpload(connection_reset=False)
        return super().new_file(field_name, *args, **kwargs)

    def receive_data_chunk(self, raw_data, start):
        self.total += len(raw_data)
        if self.total > MAX_UPLOAD_BYTES:
            self.request._avatar_upload_rejected = True
            raise StopUpload(connection_reset=False)
        return raw_data

    def file_complete(self, file_size):
        return None
