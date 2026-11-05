"""Metadados no PostgreSQL; imagens e miniaturas em armazenamento privado."""
import uuid
from django.db import models


class ProductPhotoAsset(models.Model):
    # Registro anterior ao upload: permite recolher sobras até após interrupção do processo.
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    store = models.ForeignKey('organizations.Store', on_delete=models.PROTECT)
    company_id_snapshot = models.BigIntegerField()
    storage = models.CharField(max_length=10, choices=[('local', 'Local'), ('r2', 'R2')])
    created_at = models.DateTimeField(auto_now_add=True)

    def key(self, variant):
        return f'lentis/products/{self.company_id_snapshot}/{self.store_id}/{self.pk}/{variant}.jpg'


class ProductPhoto(models.Model):
    product = models.ForeignKey('organizations.Product', on_delete=models.CASCADE, related_name='photos')
    slot = models.PositiveSmallIntegerField()
    asset = models.OneToOneField(ProductPhotoAsset, on_delete=models.PROTECT, related_name='photo')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['slot']
        constraints = [
            models.CheckConstraint(condition=models.Q(slot__range=(1, 3)), name='product_photo_slot_valid'),
            models.UniqueConstraint(fields=['product', 'slot'], name='product_photo_unique_slot'),
        ]
