from rest_framework import serializers
from .commercial_services import decide_discount, request_discount
from .views import SalesBaseView, model_errors


class DiscountReasonSerializer(serializers.Serializer):
    reason = serializers.CharField(max_length=255,allow_blank=False)


class DiscountDecisionSerializer(DiscountReasonSerializer):
    action = serializers.ChoiceField(choices=['approve','reject'])


class RequestDiscountView(SalesBaseView):
    def post(self,request,sale_id):
        sale = self.selected_sale(sale_id)
        values = self.write_serializer(DiscountReasonSerializer,request.data,sale.store).validated_data
        with model_errors():
            return self.output(request_discount(user=request.user,sale_id=sale.pk,**values))


class DecideDiscountView(SalesBaseView):
    def post(self,request,sale_id,request_id):
        sale = self.selected_sale(sale_id)
        values = self.write_serializer(DiscountDecisionSerializer,request.data,sale.store).validated_data
        with model_errors():
            return self.output(decide_discount(user=request.user,sale_id=sale.pk,request_id=request_id,**values))
