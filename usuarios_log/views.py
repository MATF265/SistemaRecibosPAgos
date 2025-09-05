from rest_framework import generics, permissions
from rest_framework_simplejwt.views import TokenObtainPairView
from django.contrib.auth import get_user_model
from .serializers import RegisterSerializer, LoginSerializer

User = get_user_model()

class RegisterView(generics.CreateAPIView):
    permission_classes = [permissions.AllowAny]
    serializer_class = RegisterSerializer

class LoginView(TokenObtainPairView):
    permission_classes = [permissions.AllowAny]
    serializer_class = LoginSerializer

class UserListView(generics.ListAPIView):
    queryset = User.objects.all()
    serializer_class = RegisterSerializer
    permission_classes = [permissions.IsAuthenticated]
    
class UserUpdateView(generics.UpdateAPIView):
    queryset = User.objects.all()
    serializer_class = RegisterSerializer
    permission_classes = [permissions.IsAuthenticated]
    http_method_names = ["patch"]