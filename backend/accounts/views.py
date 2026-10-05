from rest_framework.generics import ListAPIView
from rest_framework.permissions import IsAuthenticated

from .selectors import get_accessible_stores
from .serializers import AccessibleStoreSerializer


class MyStoresView(ListAPIView):
    serializer_class = AccessibleStoreSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return get_accessible_stores(self.request.user)