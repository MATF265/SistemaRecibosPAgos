import csv, io, datetime, re
from decimal import Decimal, InvalidOperation
from django.contrib.auth import get_user_model
from django.db import transaction
from rest_framework.parsers import MultiPartParser, FormParser
from rest_framework import viewsets, permissions, status
from rest_framework.response import Response
from rest_framework.decorators import action
from django.db.models import Q
from django.utils import timezone
from .models import Recibo
from .serializers import ReciboSerializer
from django.db.models import Sum, Count, Case, When, F, DecimalField, Value, Q
from django.db.models.functions import TruncMonth, Coalesce
from transferencias.models import Transferencia

class EsAdmin(permissions.BasePermission):
    def has_permission(self, request, view):
        return request.user.is_authenticated and getattr(request.user, "role", 0) == 1
User = get_user_model()
class ReciboViewSet(viewsets.ModelViewSet):
    queryset = Recibo.objects.all().order_by("-creado_en")
    serializer_class = ReciboSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        qs = super().get_queryset()
        user = self.request.user
        if getattr(user, "role", 0) != 1 and not user.is_superuser:
            qs = qs.filter(Q(emisor=user) | Q(receptor=user))

        mine = self.request.query_params.get("mine")
        if mine == "issued":
            qs = qs.filter(emisor=user)
        elif mine == "received":
            qs = qs.filter(receptor=user)

        status_param = self.request.query_params.get("status")
        if status_param in ("PENDING", "PAID"):
            qs = qs.filter(status=status_param)
        return qs

    def perform_create(self, serializer):
        serializer.save()

    def update(self, request, *args, **kwargs):
        return super().update(request, *args, **kwargs)

    def partial_update(self, request, *args, **kwargs):
        recibo = self.get_object()
        user = request.user

        if getattr(user, "role", 0) != 1 and not user.is_superuser:
            if recibo.emisor_id != user.id:
                return Response({"detail": "No puedes editar este recibo."}, status=403)
            if recibo.status != Recibo.Status.PENDIENTE:
                return Response({"detail": "No puedes editar un recibo pagado."}, status=400)
        return super().partial_update(request, *args, **kwargs)

    def destroy(self, request, *args, **kwargs):
        recibo = self.get_object()
        user = request.user

        if getattr(user, "role", 0) == 1 or user.is_superuser:
            return super().destroy(request, *args, **kwargs)
        if recibo.emisor_id == user.id and recibo.status == Recibo.Status.PENDIENTE:
            return super().destroy(request, *args, **kwargs)
        return Response({"detail": "No puedes borrar este recibo."}, status=403)

    @action(detail=True, methods=["post"])
    def pay(self, request, pk=None):
        """Marca el recibo como pagado (puede hacerlo el receptor o admin)."""
        recibo = self.get_object()
        user = request.user

        if recibo.status != Recibo.Status.PENDIENTE:
            return Response({"detail": "El recibo ya está pagado."}, status=400)

        if getattr(user, "role", 0) != 1 and not user.is_superuser:
            if recibo.receptor_id != user.id:
                return Response({"detail": "Solo el receptor puede pagar este recibo."}, status=403)

        recibo.status = Recibo.Status.PAGADO
        recibo.pagado_en = timezone.now()
        recibo.save()
        return Response({"detail": "Pago registrado correctamente."}, status=200)
    
    @action(
        detail=False,
        methods=["post"],
        url_path="import-csv",
        permission_classes=[permissions.IsAuthenticated, EsAdmin],
        parser_classes=[MultiPartParser, FormParser],
    )
    def import_csv(self, request):
        """
        Carga masiva de recibos desde CSV.
        SOLO CREA RECIBOS (no paga ni cambia status).
        El EMISOR SIEMPRE ES EL USUARIO AUTENTICADO (request.user).

        CSV requerido:
          receptor_id,monto,fecha
        Opcional:
          descripcion

        Fecha aceptada en: YYYY-MM-DD, DD/MM/YYYY, MM/DD/YYYY o serial Excel (días desde 1899-12-30).
        Reglas:
          - receptor_id DEBE existir (User.pk)
          - emisor (request.user) != receptor
          - monto > 0 (se toleran comas/símbolos)
        """
        if "file" not in request.FILES:
            return Response({"detail": "Falta el archivo CSV en el campo 'file'."}, status=400)

        try:
            content = request.FILES["file"].read().decode("utf-8-sig")
        except UnicodeDecodeError:
            return Response({"detail": "El archivo debe estar en UTF-8."}, status=400)

        reader = csv.DictReader(io.StringIO(content))
        required = {"receptor_id", "monto", "fecha"}
        headers = set([h.strip() for h in (reader.fieldnames or [])])

        if not required.issubset(headers):
            return Response({
                "detail": "Encabezados requeridos: receptor_id,monto,fecha (descripcion opcional)"
            }, status=400)

        emisor = request.user
        inserted = 0
        errors = []

        def parse_monto(raw):
            """
            Convierte strings de monto a Decimal tolerando formatos comunes:
            - "$1,234.50" -> 1234.50
            - "1.234,50" (europeo) -> 1234.50
            - "1234" -> 1234
            """
            s = (raw or "").strip()
            if not s:
                raise InvalidOperation()
            if re.search(r"\d\.\d{3}(?:\.\d{3})*,\d{2}$", s):
                s = s.replace(".", "").replace(",", ".")
            else:
                # Quita separadores de miles comunes y símbolos
                s = re.sub(r"[^\d.,-]", "", s)  # deja solo dígitos . , -
                # Si hay más de una coma, quítalas; usa punto como decimal
                if s.count(",") == 1 and s.count(".") == 0:
                    s = s.replace(",", ".")
                s = s.replace(",", "")
            return Decimal(s)

        def parse_fecha(raw):
            """
            Acepta 'YYYY-MM-DD', 'DD/MM/YYYY', 'MM/DD/YYYY' o serial Excel.
            """
            s = (raw or "").strip()
            if not s:
                raise ValueError("vacía")

            # Intentos por formato explícito
            for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y"):
                try:
                    return datetime.datetime.strptime(s, fmt).date()
                except Exception:
                    pass

            try:
                serial = int(s)
                base = datetime.date(1899, 12, 30)  # base típica Excel (cuenta el bug del 1900)
                return base + datetime.timedelta(days=serial)
            except Exception:
                pass

            raise ValueError(f"Formato de fecha no soportado: {s}")

        for i, row in enumerate(reader, start=2):
            
            row = {k: (v.strip() if isinstance(v, str) else v) for k, v in row.items()}

            receptor_id = row.get("receptor_id") or ""
            monto_raw   = row.get("monto") or ""
            fecha_raw   = row.get("fecha") or ""
            descripcion = row.get("descripcion") or ""

            
            try:
                receptor = User.objects.get(pk=int(receptor_id))
            except Exception:
                errors.append({"row": i, "error": f"Receptor no existe (id={receptor_id})."})
                continue


            if emisor.id == receptor.id:
                errors.append({"row": i, "error": "Emisor y receptor no pueden ser el mismo usuario."})
                continue

            try:
                monto = parse_monto(monto_raw)
                if monto <= 0:
                    raise InvalidOperation()
            except Exception:
                errors.append({"row": i, "error": f"Monto inválido: {monto_raw}"})
                continue


            try:
                fecha_obj = parse_fecha(fecha_raw)
            except Exception as e:
                errors.append({"row": i, "error": f"Fecha inválida: {fecha_raw} ({e})"})
                continue

            try:
                with transaction.atomic():
                    Recibo.objects.create(
                        emisor=emisor,  
                        receptor=receptor,
                        monto=monto,
                        fecha=fecha_obj,
                        descripcion=descripcion,
                    )
                    inserted += 1
            except Exception as e:
                errors.append({"row": i, "error": f"Error al guardar: {str(e)}"})
                continue

        return Response({"inserted": inserted, "errors": errors}, status=200)
    
    @action(detail=False, methods=["get"], url_path="stats/summary", permission_classes=[permissions.IsAuthenticated, EsAdmin])
    def stats_summary(self, request):
        qs = Recibo.objects.all()

        dec0 = Value(0, output_field=DecimalField(max_digits=12, decimal_places=2))

        sum_total        = qs.aggregate(s=Coalesce(Sum("monto"), dec0))["s"]
        pending_qs       = qs.filter(status=Recibo.Status.PENDIENTE)
        paid_qs          = qs.filter(status=Recibo.Status.PAGADO)
        sum_pendiente    = pending_qs.aggregate(s=Coalesce(Sum("monto"), dec0))["s"]
        sum_pagado       = paid_qs.aggregate(s=Coalesce(Sum("monto"), dec0))["s"]

        return Response({
            "recibos": {
                "total": qs.count(),
                "pendientes": pending_qs.count(),
                "pagados": paid_qs.count(),
                "monto_total": float(sum_total or 0),
                "monto_pendiente": float(sum_pendiente or 0),
                "monto_pagado": float(sum_pagado or 0),
            }
        })

    @action(detail=False, methods=["get"], url_path="stats/monthly", permission_classes=[permissions.IsAuthenticated, EsAdmin])
    def stats_monthly(self, request):
        year = int(request.query_params.get("year", timezone.now().year))
        qs = Recibo.objects.filter(fecha__year=year)

        dec0 = Value(0, output_field=DecimalField(max_digits=12, decimal_places=2))

        monthly = (
            qs.annotate(month=TruncMonth("fecha"))
            .values("month")
            .annotate(
                count=Count("id"),
                total_monto=Coalesce(Sum("monto"), dec0),

                pendientes=Count("id", filter=Q(status=Recibo.Status.PENDIENTE)),
                pagados=Count("id",   filter=Q(status=Recibo.Status.PAGADO)),

                monto_pendiente=Coalesce(
                    Sum("monto",
                        filter=Q(status=Recibo.Status.PENDIENTE),
                        output_field=DecimalField(max_digits=12, decimal_places=2)),
                    dec0
                ),
                monto_pagado=Coalesce(
                    Sum("monto",
                        filter=Q(status=Recibo.Status.PAGADO),
                        output_field=DecimalField(max_digits=12, decimal_places=2)),
                    dec0
                ),
            )
            .order_by("month")
        )

        data = []
        for row in monthly:
            m = row["month"]
            data.append({
                "month": m.strftime("%Y-%m"),
                "count": row["count"],
                "monto_total": float(row["total_monto"] or 0),
                "pendientes": row["pendientes"],
                "pagados": row["pagados"],
                "monto_pendiente": float(row["monto_pendiente"] or 0),
                "monto_pagado": float(row["monto_pagado"] or 0),
            })
        return Response({"year": year, "series": data})

    @action(detail=False, methods=["get"], url_path="stats/top-debtors",
            permission_classes=[permissions.IsAuthenticated, EsAdmin])
    def stats_top_debtors(self, request):
        limit = int(request.query_params.get("limit", 10))

        dec0 = Value(0, output_field=DecimalField(max_digits=12, decimal_places=2))

        pending = (
            Recibo.objects.filter(status=Recibo.Status.PENDIENTE)
            .values("receptor_id", "receptor__username", "receptor__first_name", "receptor__last_name")
            .annotate(
                monto_pendiente=Coalesce(Sum("monto"), dec0),
                count=Count("id"),
            )
            .order_by("-monto_pendiente")[:limit]
        )

        items = []
        for r in pending:
            name = (f'{r["receptor__first_name"]} {r["receptor__last_name"]}'.strip() or r["receptor__username"])
            items.append({
                "user_id": r["receptor_id"],
                "display_name": name,
                "count": r["count"],
                "monto_pendiente": float(r["monto_pendiente"] or 0),
            })

        return Response({"limit": limit, "items": items})

    @action(detail=False, methods=["get"], url_path="stats/aging", permission_classes=[permissions.IsAuthenticated, EsAdmin])
    def stats_aging(self, request):
        b1 = int(request.query_params.get("b1", 30))
        b2 = int(request.query_params.get("b2", 60))
        today = timezone.now().date()

        pend = Recibo.objects.filter(status=Recibo.Status.PENDIENTE).annotate(
            dias=(Value(today, output_field=DecimalField()) - F("fecha"))
        )
        buckets = {
            f"0-{b1}": {"count": 0, "monto": Decimal("0")},
            f"{b1+1}-{b2}": {"count": 0, "monto": Decimal("0")},
            f">{b2}": {"count": 0, "monto": Decimal("0")},
        }

        for r in Recibo.objects.filter(status=Recibo.Status.PENDIENTE).only("id", "monto", "fecha"):
            dias = (today - r.fecha).days
            if dias <= b1:
                key = f"0-{b1}"
            elif dias <= b2:
                key = f"{b1+1}-{b2}"
            else:
                key = f">{b2}"
            buckets[key]["count"] += 1
            buckets[key]["monto"] += r.monto

        out = {k: {"count": v["count"], "monto": float(v["monto"])} for k, v in buckets.items()}
        return Response({"as_of": today.isoformat(), "buckets": out})                

    @action(detail=False, methods=["get"], url_path=r"stats/user/(?P<user_id>\d+)",
            permission_classes=[permissions.IsAuthenticated, EsAdmin])
    def stats_user(self, request, user_id=None):
        try:
            u = User.objects.get(pk=int(user_id))
        except User.DoesNotExist:
            return Response({"detail": "Usuario no encontrado"}, status=404)

        dec0 = Value(0, output_field=DecimalField(max_digits=12, decimal_places=2))
        year = int(request.query_params.get("year", timezone.now().year))

        emitidos_qs  = Recibo.objects.filter(emisor=u)
        recibidos_qs = Recibo.objects.filter(receptor=u)
        pagado_qs    = Transferencia.objects.filter(pagador=u)

        emitidos_total = emitidos_qs.count()
        emitidos_total_monto = emitidos_qs.aggregate(s=Coalesce(Sum("monto"), dec0))["s"]

        recibidos_total = recibidos_qs.count()
        recibidos_total_monto = recibidos_qs.aggregate(s=Coalesce(Sum("monto"), dec0))["s"]

        debe_monto = recibidos_qs.filter(status=Recibo.Status.PENDIENTE) \
            .aggregate(s=Coalesce(Sum("monto"), dec0))["s"]

        cobrado_monto = emitidos_qs.filter(status=Recibo.Status.PAGADO) \
            .aggregate(s=Coalesce(Sum("monto"), dec0))["s"]

        pagado_monto = pagado_qs.aggregate(s=Coalesce(Sum("monto"), dec0))["s"]

        saldo = (cobrado_monto or 0) - (pagado_monto or 0)

        em_series = (
            emitidos_qs.filter(fecha__year=year)
            .annotate(m=TruncMonth("fecha"))
            .values("m")
            .annotate(
                count=Count("id"),
                total_monto=Coalesce(Sum("monto"), dec0),
            )
            .order_by("m")
        )
        rc_series = (
            recibidos_qs.filter(fecha__year=year)
            .annotate(m=TruncMonth("fecha"))
            .values("m")
            .annotate(
                count=Count("id"),
                total_monto=Coalesce(Sum("monto"), dec0),
            )
            .order_by("m")
        )

        def serialize_monthly(rows):
            return [
                {
                    "month": r["m"].strftime("%Y-%m"),
                    "count": r["count"],
                    "monto": float(r["total_monto"] or 0),
                }
                for r in rows
            ]

        display_name = (f"{u.first_name} {u.last_name}".strip() or u.username)

        return Response({
            "user": {"id": u.id, "username": u.username, "display_name": display_name},
            "emitidos": {"count": emitidos_total, "monto": float(emitidos_total_monto or 0)},
            "recibidos": {"count": recibidos_total, "monto": float(recibidos_total_monto or 0)},
            "pagado_por_el_usuario": float(pagado_monto or 0),
            "debe": float(debe_monto or 0),
            "cobrado": float(cobrado_monto or 0),
            "saldo": float(saldo or 0),
            "series": {
                "year": year,
                "emitidos": serialize_monthly(em_series),
                "recibidos": serialize_monthly(rc_series),
            },
        })

    @action(
        detail=False,
        methods=["get"],
        url_path="user-overview",
        permission_classes=[permissions.IsAuthenticated, EsAdmin],
    )
    def stats_user_overview(self, request):
        """
        Devuelve:
        - emitidos_count: # de recibos emitidos por el usuario
        - recibidos_count: # de recibos recibidos por el usuario
        - pagos_count: # de transferencias realizadas por el usuario
        - sum_pagado: suma de transferencias realizadas por el usuario
        - sum_pendiente_pagar: suma de recibos PENDIENTES donde es receptor
        - saldo = sum_pagado - sum_pendiente_pagar
        """
        user_id = request.query_params.get("user_id")
        if user_id:
            try:
                u = User.objects.get(pk=int(user_id))
            except User.DoesNotExist:
                return Response({"detail": "Usuario no encontrado"}, status=404)
        else:
            u = request.user


        dec0 = Value(0, output_field=DecimalField(max_digits=12, decimal_places=2))

        emitidos_count   = Recibo.objects.filter(emisor=u).count()
        recibidos_count  = Recibo.objects.filter(receptor=u).count()
        pagos_count      = Transferencia.objects.filter(pagador=u).count()

        sum_pagado = Transferencia.objects.filter(pagador=u).aggregate(s=Coalesce(Sum("monto"), dec0))["s"]
        sum_pendiente_pagar = Recibo.objects.filter(
            receptor=u, status=Recibo.Status.PENDIENTE
        ).aggregate(s=Coalesce(Sum("monto"), dec0))["s"]

        saldo = (sum_pagado or 0) - (sum_pendiente_pagar or 0)

        display_name = (f"{u.first_name} {u.last_name}".strip() or u.username)

        return Response({
            "user": {"id": u.id, "username": u.username, "display_name": display_name},
            "emitidos_count": emitidos_count,
            "recibidos_count": recibidos_count,
            "pagos_count": pagos_count,
            "sum_pagado": float(sum_pagado or 0),
            "sum_pendiente_pagar": float(sum_pendiente_pagar or 0),
            "saldo": float(saldo or 0),
        })