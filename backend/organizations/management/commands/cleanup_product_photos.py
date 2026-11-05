from datetime import timedelta
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone
from organizations.product_photo_models import ProductPhotoAsset
from organizations.product_photo_services import purge_asset


class Command(BaseCommand):
    help = 'Lista sobras de fotos com mais de 24h. Use --apply para removê-las do armazenamento e do banco.'

    def add_arguments(self, parser):
        parser.add_argument('--apply', action='store_true')

    def handle(self, *args, **options):
        cutoff = timezone.now() - timedelta(hours=24)
        ids = ProductPhotoAsset.objects.filter(photo__isnull=True, created_at__lt=cutoff).values_list('pk', flat=True)
        count = 0
        for pk in ids.iterator():
            if not options['apply']:
                count += 1
                continue
            try:
                with transaction.atomic():
                    asset = ProductPhotoAsset.objects.select_for_update().filter(pk=pk, photo__isnull=True).first()
                    if asset and purge_asset(asset):
                        count += 1
            except Exception as exc:
                raise CommandError('Não foi possível limpar uma sobra de foto. O registro foi preservado para nova tentativa.') from exc
        self.stdout.write(f'{count} sobra(s) ' + ('removida(s).' if options['apply'] else 'encontrada(s). Nenhum arquivo removido; use --apply para confirmar.'))
