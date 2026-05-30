from django.contrib import admin
from .models import AuditLog, SuspiciousActivity

@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    list_display = ['id', 'action_type', 'timestamp', 'current_hash']
    list_filter = ['action_type', 'timestamp']
    search_fields = ['payload']
    readonly_fields = ['action_type', 'payload', 'timestamp', 'current_hash', 'previous_hash']

    def has_add_permission(self, request):
        return False
        
    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(SuspiciousActivity)
class SuspiciousActivityAdmin(admin.ModelAdmin):
    list_display = ['id', 'rule_triggered', 'severity', 'status', 'created_at']
    list_filter = ['rule_triggered', 'severity', 'status', 'created_at']
    readonly_fields = ['user', 'rule_triggered', 'severity', 'details', 'status', 'created_at']

    def has_add_permission(self, request):
        return False
