from django.db import models
from django.conf import settings
from django.utils import timezone
from recibos.models import Recibo

User = settings.AUTH_USER_MODEL

class Transferencia(models.Model):
    recibo = models.OneToOneField(Recibo, on_delete=models.CASCADE, related_name="transferencia")
    pagador = models.ForeignKey(User, on_delete=models.CASCADE, related_name="transferencias_realizadas")
    monto = models.DecimalField(max_digits=12, decimal_places=2)
    fecha = models.DateTimeField(default=timezone.now)
    referencia = models.CharField(max_length=100, blank=True, null=True)
    nota = models.TextField(blank=True, null=True)

    def __str__(self):
        return f"Transferencia #{self.id} de {self.pagador} por {self.monto}"
