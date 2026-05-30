from django.shortcuts import render
from django.http import JsonResponse
from django.contrib.auth.decorators import user_passes_test
from django.views.decorators.http import require_GET
from .models import AuditLog

# Decorador para asegurar que solo usuarios staff/admin puedan acceder
@user_passes_test(lambda u: u.is_authenticated and u.is_staff)
@require_GET
def verify_audit_chain_api(request):
    """
    Endpoint administrativo para verificar en tiempo real la integridad 
    de la cadena de bloques del registro de auditoría.
    """
    is_valid, corrupted_id = AuditLog.verify_chain()

    if is_valid:
        return JsonResponse({
            "status": "success",
            "integrity": True,
            "message": "La cadena de auditoría es completamente íntegra. No se detectaron alteraciones."
        }, status=200)
    else:
        return JsonResponse({
            "status": "danger",
            "integrity": False,
            "message": "¡ALERTA DE INTEGRIDAD! Se ha detectado una alteración maliciosa en los registros financieros o de apuestas.",
            "corrupted_block_id": corrupted_id
        }, status=400)
# Create your views here.
