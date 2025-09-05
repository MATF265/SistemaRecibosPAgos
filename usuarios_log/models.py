from django.contrib.auth.models import AbstractUser
from django.db import models

class User(AbstractUser):
    class Roles(models.IntegerChoices):
        CLIENTE = 0, "Cliente"
        ADMIN   = 1, "Administrador"

    role = models.IntegerField(choices=Roles.choices, default=Roles.CLIENTE)

    def __str__(self):
        return f"{self.username} ({self.get_role_display()})"
