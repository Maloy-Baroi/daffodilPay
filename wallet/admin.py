# wallet/admin.py
from django.contrib import admin
from django.utils.html import format_html
from django.urls import reverse
from django.utils.safestring import mark_safe
from .models import UserProfile, Wallet, Card, Transaction, TransactionLog


@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    """Admin interface for User Profiles"""
    list_display = [
        'user', 'full_name', 'current_city', 'current_country',
        'phone_number', 'is_verified', 'created_at'
    ]
    list_filter = [
        'current_country', 'is_verified', 'created_at', 'updated_at'
    ]
    search_fields = [
        'user__username', 'user__email', 'user__first_name',
        'user__last_name', 'current_city', 'phone_number'
    ]
    readonly_fields = ['created_at', 'updated_at']
    fieldsets = (
        ('User Information', {
            'fields': ('user', 'phone_number', 'date_of_birth', 'profile_picture')
        }),
        ('Location', {
            'fields': ('current_city', 'current_country')
        }),
        ('Status', {
            'fields': ('is_verified',)
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )

    def full_name(self, obj):
        return obj.full_name

    full_name.short_description = 'Full Name'


@admin.register(Wallet)
class WalletAdmin(admin.ModelAdmin):
    """Admin interface for Wallets"""
    list_display = [
        'user', 'balance', 'currency', 'is_active',
        'daily_limit', 'monthly_limit', 'created_at'
    ]
    list_filter = ['currency', 'is_active', 'created_at']
    search_fields = ['user__username', 'user__email']
    readonly_fields = ['created_at', 'updated_at']
    fieldsets = (
        ('Wallet Information', {
            'fields': ('user', 'balance', 'currency', 'is_active')
        }),
        ('Limits', {
            'fields': ('daily_limit', 'monthly_limit')
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )

    def get_readonly_fields(self, request, obj=None):
        # Make balance readonly for safety
        readonly_fields = list(self.readonly_fields)
        if obj:  # Editing existing object
            readonly_fields.append('balance')
        return readonly_fields


@admin.register(Card)
class CardAdmin(admin.ModelAdmin):
    """Admin interface for Cards"""
    list_display = [
        'user', 'card_type', 'masked_number', 'card_holder_name',
        'is_active', 'is_default', 'created_at'
    ]
    list_filter = ['card_type', 'is_active', 'is_default', 'created_at']
    search_fields = [
        'user__username', 'card_holder_name', 'card_number'
    ]
    readonly_fields = ['created_at', 'masked_number']
    fieldsets = (
        ('Card Information', {
            'fields': ('user', 'card_type', 'card_holder_name', 'masked_number')
        }),
        ('Card Details', {
            'fields': ('card_number', 'expiry_month', 'expiry_year', 'cvv'),
            'classes': ('collapse',)
        }),
        ('Status', {
            'fields': ('is_active', 'is_default')
        }),
        ('Timestamps', {
            'fields': ('created_at',),
            'classes': ('collapse',)
        }),
    )

    def masked_number(self, obj):
        return obj.masked_number

    masked_number.short_description = 'Card Number'

    def get_readonly_fields(self, request, obj=None):
        readonly_fields = list(self.readonly_fields)
        if obj:  # Editing existing object
            readonly_fields.extend(['card_number', 'cvv'])
        return readonly_fields


class TransactionLogInline(admin.TabularInline):
    """Inline admin for Transaction Logs"""
    model = TransactionLog
    extra = 0
    readonly_fields = ['created_at', 'changed_by']
    fields = ['previous_status', 'new_status', 'reason', 'changed_by', 'created_at']


@admin.register(Transaction)
class TransactionAdmin(admin.ModelAdmin):
    """Admin interface for Transactions"""
    list_display = [
        'transaction_id_short', 'user', 'transaction_type_display',
        'amount', 'fee', 'total_amount', 'status_colored', 'created_at'
    ]
    list_filter = [
        'transaction_type', 'status', 'created_at', 'completed_at'
    ]
    search_fields = [
        'transaction_id', 'user__username', 'mobile_number',
        'description', 'reference_number'
    ]
    readonly_fields = [
        'transaction_id', 'total_amount', 'created_at',
        'completed_at', 'failed_at', 'ip_address'
    ]
    date_hierarchy = 'created_at'
    inlines = [TransactionLogInline]

    fieldsets = (
        ('Transaction Information', {
            'fields': (
                'transaction_id', 'user', 'transaction_type',
                'amount', 'fee', 'total_amount', 'status'
            )
        }),
        ('Related Objects', {
            'fields': ('card', 'recipient_user'),
            'classes': ('collapse',)
        }),
        ('Payment Details', {
            'fields': ('mobile_number', 'description', 'reference_number'),
            'classes': ('collapse',)
        }),
        ('Metadata', {
            'fields': ('ip_address', 'user_agent'),
            'classes': ('collapse',)
        }),
        ('Timestamps', {
            'fields': ('created_at', 'completed_at', 'failed_at'),
            'classes': ('collapse',)
        }),
    )

    def transaction_id_short(self, obj):
        return str(obj.transaction_id)[:8] + '...'

    transaction_id_short.short_description = 'Transaction ID'

    def transaction_type_display(self, obj):
        return obj.get_transaction_type_display()

    transaction_type_display.short_description = 'Type'

    def status_colored(self, obj):
        colors = {
            'pending': 'orange',
            'processing': 'blue',
            'completed': 'green',
            'failed': 'red',
            'cancelled': 'gray'
        }
        color = colors.get(obj.status, 'black')
        return format_html(
            '<span style="color: {};">{}</span>',
            color,
            obj.get_status_display()
        )

    status_colored.short_description = 'Status'

    def get_readonly_fields(self, request, obj=None):
        readonly_fields = list(self.readonly_fields)
        if obj:  # Editing existing object
            readonly_fields.extend(['user', 'transaction_type', 'amount'])
        return readonly_fields

    actions = ['mark_completed', 'mark_failed', 'mark_cancelled']

    def mark_completed(self, request, queryset):
        """Mark selected transactions as completed"""
        from django.utils import timezone
        count = 0
        for transaction in queryset.filter(status__in=['pending', 'processing']):
            transaction.status = 'completed'
            transaction.completed_at = timezone.now()
            transaction.save()

            # Create log entry
            TransactionLog.objects.create(
                transaction=transaction,
                previous_status='pending',
                new_status='completed',
                reason='Marked completed by admin',
                changed_by=request.user
            )
            count += 1

        self.message_user(request, f'{count} transactions marked as completed.')

    mark_completed.short_description = 'Mark selected transactions as completed'

    def mark_failed(self, request, queryset):
        """Mark selected transactions as failed"""
        from django.utils import timezone
        count = 0
        for transaction in queryset.filter(status__in=['pending', 'processing']):
            transaction.status = 'failed'
            transaction.failed_at = timezone.now()
            transaction.save()

            # Create log entry
            TransactionLog.objects.create(
                transaction=transaction,
                previous_status='pending',
                new_status='failed',
                reason='Marked failed by admin',
                changed_by=request.user
            )
            count += 1

        self.message_user(request, f'{count} transactions marked as failed.')

    mark_failed.short_description = 'Mark selected transactions as failed'

    def mark_cancelled(self, request, queryset):
        """Mark selected transactions as cancelled"""
        count = 0
        for transaction in queryset.filter(status__in=['pending', 'processing']):
            transaction.status = 'cancelled'
            transaction.save()

            # Create log entry
            TransactionLog.objects.create(
                transaction=transaction,
                previous_status='pending',
                new_status='cancelled',
                reason='Cancelled by admin',
                changed_by=request.user
            )
            count += 1

        self.message_user(request, f'{count} transactions cancelled.')

    mark_cancelled.short_description = 'Cancel selected transactions'


@admin.register(TransactionLog)
class TransactionLogAdmin(admin.ModelAdmin):
    """Admin interface for Transaction Logs"""
    list_display = [
        'transaction_id_short', 'previous_status', 'new_status',
        'changed_by', 'created_at'
    ]
    list_filter = ['previous_status', 'new_status', 'created_at']
    search_fields = ['transaction__transaction_id', 'reason']
    readonly_fields = ['created_at']
    date_hierarchy = 'created_at'

    def transaction_id_short(self, obj):
        return str(obj.transaction.transaction_id)[:8] + '...'

    transaction_id_short.short_description = 'Transaction ID'

    def get_readonly_fields(self, request, obj=None):
        if obj:  # Editing existing object
            return ['transaction', 'previous_status', 'new_status', 'changed_by', 'created_at']
        return self.readonly_fields


# Customize admin site
admin.site.site_header = "Digital Wallet Administration"
admin.site.site_title = "Digital Wallet Admin"
admin.site.index_title = "Welcome to Digital Wallet Administration"