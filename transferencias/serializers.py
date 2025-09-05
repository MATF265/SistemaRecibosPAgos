from rest_framework import serializers
from .models import Transferencia

class TransferenciaSerializer(serializers.ModelSerializer):
    recibo_id = serializers.IntegerField(write_only=True)

    class Meta:
        model = Transferencia
        fields = ["id", "recibo_id", "pagador", "monto", "fecha", "referencia", "nota"]
        read_only_fields = ["pagador", "fecha"]

    def create(self, validated_data):
        user = self.context["request"].user
        validated_data["pagador"] = user
        return super().create(validated_data)
