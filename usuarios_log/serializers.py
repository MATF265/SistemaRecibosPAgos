from django.contrib.auth import get_user_model
from rest_framework import serializers
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer

User = get_user_model()

class RegisterSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, min_length=6)

    class Meta:
        model = User
        fields = ["id","username","email","password","role", "first_name", "last_name", "is_active"]
        extra_kwargs = {
            "username": {"error_messages": {"required": "El nombre de usuario es obligatorio."}},
        }
    def create(self, validated_data):
        pwd = validated_data.pop("password")
        user = User(**validated_data)
        user.set_password(pwd)
        user.save()
        return user

class LoginSerializer(TokenObtainPairSerializer):
    def validate(self, attrs):
        try:
            data = super().validate(attrs)
        except Exception:
            raise serializers.ValidationError("Usuario o contraseña incorrectos.")
        if not self.user.is_active:
            raise serializers.ValidationError("El usuario se encuentra inactivo, no puede iniciar sesión.")        
        data.update({
            "user": {
                "id": self.user.id,
                "username": self.user.username,
                "email": self.user.email,
                "first_name": self.user.first_name,
                "last_name": self.user.last_name,
                "role": self.user.role,
            }
        })
        return data
