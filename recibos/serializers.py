from rest_framework import serializers
from .models import Recibo

class ReciboSerializer(serializers.ModelSerializer):
    emisor_username   = serializers.ReadOnlyField(source="emisor.username")
    receptor_username = serializers.ReadOnlyField(source="receptor.username")

    class Meta:
        model = Recibo
        fields = [
            "id",
            "emisor", "emisor_username",
            "receptor", "receptor_username",
            "monto", "fecha", "descripcion",
            "status", "pagado_en", "creado_en",
        ]
        read_only_fields = ["emisor", "status", "pagado_en", "creado_en"]

    def validate(self, attrs):
        receptor = attrs.get("receptor")
        request = self.context.get("request")

        if request and request.method == "POST":
            if receptor and request.user.id == receptor.id:
                raise serializers.ValidationError("No puedes emitir un recibo para ti mismo.")
        return attrs

    def create(self, validated_data):
        validated_data["emisor"] = self.context["request"].user
        return super().create(validated_data)
