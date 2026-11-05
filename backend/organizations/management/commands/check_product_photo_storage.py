from uuid import uuid4
from django.core.management.base import BaseCommand, CommandError
from organizations.product_photo_storage import PhotoStorage


class Command(BaseCommand):
    help = 'Valida a configuração das fotos. --roundtrip também grava, lê e remove um objeto de diagnóstico.'

    def add_arguments(self, parser):
        parser.add_argument('--roundtrip', action='store_true')

    def handle(self, *args, **options):
        key = f'lentis/diagnostics/{uuid4()}/thumb.jpg'
        try:
            storage = PhotoStorage()
            if options['roundtrip']:
                from io import BytesIO
                from PIL import Image
                with Image.new('RGB', (8, 8), 'white') as image:
                    output = BytesIO(); image.save(output, 'JPEG')
                data = output.getvalue()
                try:
                    storage.put(key, data)
                    if storage.get(key, 'thumb') != data:
                        raise ValueError('Leitura diferente do envio.')
                finally:
                    storage.delete(key)
            self.stdout.write(self.style.SUCCESS(f'Armazenamento {storage.kind}: configuração válida.' +
                (' Envio, leitura e remoção conferidos.' if options['roundtrip'] else ' Nenhum acesso ao bucket foi feito.')))
        except Exception as exc:
            raise CommandError('Não foi possível conferir as fotos. Revise as variáveis LENTIS_R2_*, o bucket privado e o token com leitura e escrita. Nenhuma credencial foi exibida.') from exc
