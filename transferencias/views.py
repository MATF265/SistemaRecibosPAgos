from rest_framework import viewsets, permissions, status
from rest_framework.response import Response
from rest_framework.decorators import action
from rest_framework.parsers import MultiPartParser, FormParser
from django.db import transaction
from django.utils import timezone
from decimal import Decimal, InvalidOperation
import csv, io, datetime, re

from recibos.models import Recibo
from .models import Transferencia
from .serializers import TransferenciaSerializer

class IsAdminRole(permissions.BasePermission):
    def has_permission(self, request, view):
        return request.user.is_authenticated and getattr(request.user, "role", 0) == 1

class TransferenciaViewSet(viewsets.ModelViewSet):
    queryset = Transferencia.objects.all().order_by("-fecha")
    serializer_class = TransferenciaSerializer
    permission_classes = [permissions.IsAuthenticated]

    def perform_create(self, serializer):
        recibo_id = self.request.data.get("recibo_id")
        try:
            recibo = Recibo.objects.get(pk=recibo_id)
        except Recibo.DoesNotExist:
            raise ValueError("Recibo no encontrado")

        if recibo.status == Recibo.Status.PAGADO:
            raise ValueError("El recibo ya está pagado")

        transferencia = serializer.save(pagador=self.request.user)
        recibo.status = Recibo.Status.PAGADO
        recibo.pagado_en = transferencia.fecha
        recibo.save()

    def get_queryset(self):
        qs = super().get_queryset()
        rid = self.request.query_params.get("recibo_id")
        if rid:
            qs = qs.filter(recibo_id=rid)
        return qs

    # ========= CSV IMPORT =========
    @action(
        detail=False,
        methods=["post"],
        url_path="import-csv",
        permission_classes=[permissions.IsAuthenticated, IsAdminRole],
        parser_classes=[MultiPartParser, FormParser],
    )
    def import_csv(self, request):
        """
        Importa transferencias desde CSV y marca los recibos como PAGADO.

        CSV requerido:
        recibo_id,monto
        Opcional:
        referencia,nota,fecha

        Reglas:
        - recibo_id debe existir y NO estar pagado
        - pagador = request.user
        - monto > 0 y debe coincidir con el monto del recibo
        - fecha: si no viene → se usa la actual; si viene, acepta:
                YYYY-MM-DD, DD/MM/YYYY, MM/DD/YYYY o serial Excel (base 1899-12-30)
        """
        if "file" not in request.FILES:
            return Response({"detail": "Falta el archivo CSV en el campo 'file'."}, status=400)

        # leer archivo
        try:
            content = request.FILES["file"].read().decode("utf-8-sig")
        except UnicodeDecodeError:
            return Response({"detail": "El archivo debe estar en UTF-8."}, status=400)

        reader = csv.DictReader(io.StringIO(content))
        required = {"recibo_id", "monto"}
        headers = set([h.strip() for h in (reader.fieldnames or [])])
        if not required.issubset(headers):
            return Response({
                "detail": "Encabezados requeridos: recibo_id,monto (referencia,nota,fecha opcionales)"
            }, status=400)

        def parse_monto(raw: str) -> Decimal:
            """Tolera '$1,234.50', '1.234,50', '1234'."""
            s = (raw or "").strip()
            if not s:
                raise InvalidOperation()
            # europeo 1.234,56
            if re.search(r"\d\.\d{3}(?:\.\d{3})*,\d{2}$", s):
                s = s.replace(".", "").replace(",", ".")
            else:
                s = re.sub(r"[^\d.,-]", "", s)
                if s.count(",") == 1 and s.count(".") == 0:
                    s = s.replace(",", ".")
                s = s.replace(",", "")
            return Decimal(s)

        def parse_fecha_dt(raw: str) -> datetime.datetime:
            """Devuelve datetime: soporta ISO, dd/mm/yyyy, mm/dd/yyyy o serial Excel."""
            s = (raw or "").strip()
            if not s:
                return timezone.now()
            for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y"):
                try:
                    d = datetime.datetime.strptime(s, fmt).date()
                    return datetime.datetime.combine(d, datetime.time.min)
                except Exception:
                    pass
            try:
                serial = int(s)
                base = datetime.date(1899, 12, 30)
                d = base + datetime.timedelta(days=serial)
                return datetime.datetime.combine(d, datetime.time.min)
            except Exception:
                pass
            raise ValueError(f"Formato de fecha no soportado: {s}")

        user = request.user
        is_admin = getattr(user, "role", 0) == 1 or user.is_superuser

        inserted = 0
        skipped = 0
        errors = []

        for i, row in enumerate(reader, start=2):
            row = {k: (v.strip() if isinstance(v, str) else v) for k, v in row.items()}

            rid_raw    = row.get("recibo_id") or ""
            monto_raw  = row.get("monto") or ""
            fecha_raw  = row.get("fecha") or ""
            referencia = row.get("referencia") or ""
            nota       = row.get("nota") or ""

            try:
                rid = int(rid_raw)
                recibo = Recibo.objects.get(pk=rid)
            except Exception:
                errors.append({"row": i, "error": f"Recibo no encontrado (id={rid_raw})."})
                skipped += 1
                continue

            if recibo.status == Recibo.Status.PAGADO:
                errors.append({"row": i, "error": f"El recibo {recibo.id} ya está pagado."})
                skipped += 1
                continue

            try:
                monto = parse_monto(monto_raw)
                if monto <= 0:
                    raise InvalidOperation()
            except Exception:
                errors.append({"row": i, "error": f"Monto inválido: {monto_raw}"})
                skipped += 1
                continue

            if monto != recibo.monto:
                errors.append({"row": i, "error": f"El monto ({monto}) no coincide con el del recibo ({recibo.monto})."})
                skipped += 1
                continue

            try:
                fecha_dt = parse_fecha_dt(fecha_raw)
            except Exception as e:
                errors.append({"row": i, "error": f"Fecha inválida: {fecha_raw} ({e})"})
                skipped += 1
                continue

            try:
                with transaction.atomic():
                    Transferencia.objects.create(
                        recibo=recibo,
                        pagador=user,
                        monto=monto,
                        fecha=fecha_dt,
                        referencia=referencia or None,
                        nota=nota or None,
                    )
                    recibo.status = Recibo.Status.PAGADO
                    recibo.pagado_en = fecha_dt
                    recibo.save(update_fields=["status", "pagado_en"])
                    inserted += 1
            except Exception as e:
                errors.append({"row": i, "error": f"Error al guardar: {str(e)}"})
                skipped += 1
                continue

        return Response({
            "inserted": inserted,
            "skipped": skipped,
            "errors": errors,
        }, status=status.HTTP_200_OK)
