from django.contrib import admin
from .models import Recibo

@admin.register(Recibo)
class ReciboAdmin(admin.ModelAdmin):
    list_display = (
        "id", "emisor", "receptor", "monto",
        "status", "fecha", "pagado_en", "creado_en",
    )
    list_filter = (
        "status",
        ("fecha", admin.DateFieldListFilter),
    )
    search_fields = (
        "descripcion",
        "emisor__username", "emisor__first_name", "emisor__last_name",
        "receptor__username", "receptor__first_name", "receptor__last_name",
    )
    autocomplete_fields = ("emisor", "receptor")
    readonly_fields = ("pagado_en", "creado_en")
    date_hierarchy = "fecha"
    ordering = ("-creado_en",)
    actions = ["marcar_pagado"]

    def marcar_pagado(self, request, queryset):
        count = 0
        for r in queryset.filter(status=Recibo.Status.PENDIENTE):
            r.marcar_pagado()
            count += 1
        self.message_user(request, f"{count} recibo(s) marcados como pagados.")
    marcar_pagado.short_description = "Marcar como pagado (solo PENDIENTE)"

    def save_model(self, request, obj, form, change):
        if not change and not obj.emisor_id:
            obj.emisor = request.user
        super().save_model(request, obj, form, change)
