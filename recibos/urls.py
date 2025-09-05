from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import ReciboViewSet

router = DefaultRouter()
router.register(r"recibos", ReciboViewSet, basename="recibo")

urlpatterns = [
    path("", include(router.urls)),
]
