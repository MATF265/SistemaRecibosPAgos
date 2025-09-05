from django.db import models
from django.conf import settings
from django.utils import timezone

User = settings.AUTH_USER_MODEL

class Recibo(models.Model):
    class Status(models.TextChoices):
        PENDIENTE = "PENDING", "Pendiente"
        PAGADO    = "PAID",    "Pagado"

    emisor   = models.ForeignKey(User, on_delete=models.CASCADE, related_name="recibos_emitidos")
    receptor = models.ForeignKey(User, on_delete=models.CASCADE, related_name="recibos_recibidos")

    monto       = models.DecimalField(max_digits=12, decimal_places=2)
    fecha       = models.DateField()
    descripcion = models.TextField(blank=True)
    status      = models.CharField(max_length=10, choices=Status.choices, default=Status.PENDIENTE)
    pagado_en   = models.DateTimeField(null=True, blank=True)
    creado_en   = models.DateTimeField(auto_now_add=True)

    def marcar_pagado(self):
        self.status = self.Status.PAGADO
        self.pagado_en = timezone.now()
        self.save()

    def __str__(self):
        return f"Recibo #{self.id} {self.emisor} → {self.receptor} | {self.monto} ({self.status})"