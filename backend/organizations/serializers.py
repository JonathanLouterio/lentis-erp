from decimal import Decimal, InvalidOperation

from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction
from rest_framework import serializers

from .models import Customer, Product, StockMovement


class ModelCleanMixin:
    @staticmethod
    def clean_instance(instance):
        try:
            instance.full_clean()
        except DjangoValidationError as exc:
            if hasattr(exc, "message_dict"):
                raise serializers.ValidationError(exc.message_dict) from exc
            raise serializers.ValidationError(exc.messages) from exc


class CustomerSerializer(ModelCleanMixin, serializers.ModelSerializer):
    store_name = serializers.CharField(source="store.name", read_only=True)

    class Meta:
        model = Customer
        fields = (
            "id", "store", "store_name", "person_type", "name", "trade_name",
            "cpf", "cnpj", "rg", "state_registration", "birth_date", "phone",
            "whatsapp", "email", "zip_code", "street", "address_number",
            "address_complement", "neighborhood", "city", "state", "notes",
            "is_active", "created_at", "updated_at",
        )
        read_only_fields = ("id", "store", "store_name", "created_at", "updated_at")

    def validate_name(self, value):
        value = value.strip()
        if not value:
            raise serializers.ValidationError("Informe o nome do cliente.")
        return value

    def validate_state(self, value):
        return value.strip().upper()

    def validate(self, attrs):
        if self.instance is None:
            return attrs
        instance = self.instance
        for field, value in attrs.items():
            setattr(instance, field, value)
        self.clean_instance(instance)
        return attrs

    def create(self, validated_data):
        instance = Customer(**validated_data)
        self.clean_instance(instance)
        instance.save()
        return instance

    def update(self, instance, validated_data):
        for field, value in validated_data.items():
            setattr(instance, field, value)
        self.clean_instance(instance)
        instance.save()
        return instance


class ProductSerializer(ModelCleanMixin, serializers.ModelSerializer):
    store_name = serializers.CharField(source="store.name", read_only=True)
    gallery = serializers.JSONField(write_only=True, required=False)
    photos = serializers.SerializerMethodField()
    thumbnail_url = serializers.SerializerMethodField()

    def get_photos(self, instance):
        from .product_photo_services import photo_output
        return photo_output(instance)

    def get_thumbnail_url(self, instance):
        from .product_photo_services import product_thumbnail
        return product_thumbnail(instance)

    def validate_gallery(self, value):
        from .product_photo_services import GalleryInput
        payload = GalleryInput(data=value)
        payload.is_valid(raise_exception=True)
        if self.instance and payload.validated_data['revision'] != self.instance.photos_revision:
            from .product_photo_services import GalleryConflict
            raise GalleryConflict()
        return payload.validated_data

    class Meta:
        model = Product
        fields = (
            "id", "store", "store_name", "internal_code", "barcode", "name",
            "brand", "category", "cost_price", "sale_price", "stock_quantity",
            "minimum_stock", "is_active", "created_at", "updated_at",
            "model_reference", "color", "material", "frame_shape", "lens_width_mm",
            "bridge_mm", "temple_mm", "description", "photos_revision", "primary_photo_slot",
            "photos", "thumbnail_url", "gallery",
        )
        read_only_fields = (
            "id", "store", "store_name", "stock_quantity", "created_at", "updated_at",
            "photos_revision", "primary_photo_slot", "photos", "thumbnail_url",
        )
        extra_kwargs = {
            "barcode": {"required": False, "allow_blank": True, "default": ""},
        }

    def validate_internal_code(self, value):
        value = value.strip()
        if not value:
            raise serializers.ValidationError("Informe o código interno.")
        return value

    def validate_name(self, value):
        value = value.strip()
        if not value:
            raise serializers.ValidationError("Informe a descrição do produto.")
        return value

    def validate(self, attrs):
        # Aceita o saldo atual enviado pelo frontend antigo, mas nunca o grava.
        # Qualquer tentativa de alterar o saldo deve usar uma movimentação.
        if "stock_quantity" in self.initial_data:
            try:
                requested = Decimal(str(self.initial_data["stock_quantity"]))
            except (InvalidOperation, TypeError, ValueError) as exc:
                raise serializers.ValidationError(
                    {"stock_quantity": "O saldo é controlado pelas movimentações."}
                ) from exc
            expected = self.instance.stock_quantity if self.instance else Decimal("0")
            if not requested.is_finite() or requested != expected:
                raise serializers.ValidationError(
                    {"stock_quantity": "Use uma movimentação para alterar o estoque."}
                )
        gallery = attrs.pop('gallery', None)
        request = self.context.get('request')
        files = request.FILES if request else {}
        self.photo_uploads = {}
        if files:
            if gallery is None:
                raise serializers.ValidationError({'gallery': 'Informe a revisão e as posições das fotos.'})
            from .product_images import normalize_product_photo
            for name, upload in files.items():
                slot = int(name[-1])
                if slot in gallery['remove']:
                    raise serializers.ValidationError({'gallery': 'Não remova e substitua a mesma posição no mesmo envio.'})
                self.photo_uploads[slot] = normalize_product_photo(upload)
        if self.instance is None:
            if gallery is not None:
                attrs['gallery'] = gallery
            return attrs
        instance = self.instance
        for field, value in attrs.items():
            setattr(instance, field, value)
        self.clean_instance(instance)
        if gallery is not None:
            attrs['gallery'] = gallery
        return attrs

    def create(self, validated_data):
        if 'gallery' in validated_data:
            from .product_photo_services import save_catalog_product
            gallery = validated_data.pop('gallery')
            return save_catalog_product(instance=None, values=validated_data, gallery=gallery,
                uploads=self.photo_uploads, actor=self.context['request'].user, clean=self.clean_instance)
        instance = Product(**validated_data)
        self.clean_instance(instance)
        instance.save()
        return instance

    def update(self, instance, validated_data):
        if 'gallery' in validated_data:
            from .product_photo_services import save_catalog_product
            gallery = validated_data.pop('gallery')
            return save_catalog_product(instance=instance, values=validated_data, gallery=gallery,
                uploads=self.photo_uploads, actor=self.context['request'].user, clean=self.clean_instance)
        # Recarrega o saldo após obter o lock: uma edição de descrição/preço
        # não pode sobrescrever uma entrada ou saída concorrente.
        with transaction.atomic():
            locked = Product.objects.select_for_update().get(pk=instance.pk)
            for field, value in validated_data.items():
                setattr(locked, field, value)
            self.clean_instance(locked)
            if validated_data:
                locked.save(update_fields=[*validated_data.keys(), "updated_at"])
            return locked


class StockMovementSerializer(serializers.ModelSerializer):
    product_name = serializers.CharField(source="product.name", read_only=True)
    product_code = serializers.CharField(source="product.internal_code", read_only=True)
    store_name = serializers.CharField(source="store.name", read_only=True)
    created_by_username = serializers.CharField(source="created_by.username", read_only=True)
    movement_type_label = serializers.CharField(source="get_movement_type_display", read_only=True)
    quantity_change = serializers.DecimalField(max_digits=13, decimal_places=3, read_only=True)

    class Meta:
        model = StockMovement
        fields = (
            "id", "store", "store_name", "product", "product_name", "product_code",
            "movement_type", "movement_type_label", "quantity", "quantity_change",
            "balance_before", "balance_after", "reason", "created_by",
            "created_by_username", "created_at",
        )
        read_only_fields = fields


class StockMovementCreateSerializer(serializers.Serializer):
    product_id = serializers.IntegerField(min_value=1, max_value=9223372036854775807)
    movement_type = serializers.ChoiceField(choices=StockMovement.MovementType.choices)
    quantity = serializers.DecimalField(max_digits=12, decimal_places=3, min_value=Decimal("0"))
    reason = serializers.CharField(max_length=255, allow_blank=False, trim_whitespace=True)

    def validate(self, attrs):
        if attrs["movement_type"] != StockMovement.MovementType.ADJUSTMENT and attrs["quantity"] <= 0:
            raise serializers.ValidationError({"quantity": "Entrada e saída devem ser maiores que zero."})
        return attrs
