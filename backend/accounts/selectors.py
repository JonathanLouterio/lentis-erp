from organizations.models import Store


def get_accessible_stores(user):
    if not user.is_authenticated or not user.is_active:
        return Store.objects.none()

    stores = Store.objects.filter(
        is_active=True,
        company__is_active=True,
    )

    if user.is_superuser:
        return stores

    return stores.filter(
        memberships__user=user,
        memberships__is_active=True,
    )
