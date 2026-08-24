"""Admin views over the authentication tables. Read-only, by design.

Staff need to see which passkeys an account holds so they can revoke one a
member has lost, and to confirm a code was issued when someone says it never
arrived. Nothing here should be editable by hand: a credential can only come
from a real WebAuthn ceremony, and a code from a real request. The code hashes
are never displayed -- there is no operational reason to read one.

The member record itself is editable, in ``accounts.admin``.
"""
from django.contrib import admin

from .models import EmailOtp, PasskeyCredential, PasskeyUserHandle


@admin.register(PasskeyCredential)
class PasskeyCredentialAdmin(admin.ModelAdmin):
    list_display = ('name', 'user', 'device_type', 'backed_up', 'created_at', 'last_used_at')
    list_filter = ('device_type', 'backed_up')
    search_fields = ('user__email', 'user__nickname', 'name')
    readonly_fields = (
        'user', 'credential_id', 'public_key', 'sign_count', 'transports',
        'aaguid', 'backed_up', 'device_type', 'created_at', 'last_used_at',
    )

    def has_add_permission(self, request):
        # A credential can only come from a real WebAuthn ceremony.
        return False


@admin.register(EmailOtp)
class EmailOtpAdmin(admin.ModelAdmin):
    list_display = ('user', 'purpose', 'created_at', 'expires_at', 'attempts', 'consumed_at')
    list_filter = ('purpose',)
    search_fields = ('user__email', 'user__nickname')
    # code_hash is deliberately absent: there is no operational reason to read it.
    fields = ('user', 'purpose', 'attempts', 'created_at', 'expires_at', 'consumed_at')
    readonly_fields = fields

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(PasskeyUserHandle)
class PasskeyUserHandleAdmin(admin.ModelAdmin):
    list_display = ('user', 'handle')
    search_fields = ('user__email', 'user__nickname')
    readonly_fields = ('user', 'handle')

    def has_add_permission(self, request):
        return False
