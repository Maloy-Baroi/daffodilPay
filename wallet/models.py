# wallet/models.py
from django.db import models
from django.contrib.auth.models import User
from django.core.validators import RegexValidator, MinValueValidator, MaxValueValidator
from django.core.exceptions import ValidationError
import uuid
from decimal import Decimal


class TimeStampedModel(models.Model):
    """Abstract base class with created_at and updated_at fields"""
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class UserProfile(TimeStampedModel):
    """Extended user profile with additional information"""
    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name='profile'
    )
    current_city = models.CharField(max_length=100)
    current_country = models.CharField(max_length=100)
    phone_number = models.CharField(
        max_length=15,
        blank=True,
        validators=[RegexValidator(
            regex=r'^\+?1?\d{9,15}$',
            message="Phone number must be entered in the format: '+999999999'. Up to 15 digits allowed."
        )]
    )
    date_of_birth = models.DateField(null=True, blank=True)
    profile_picture = models.ImageField(
        upload_to='profile_pics/',
        null=True,
        blank=True
    )
    is_verified = models.BooleanField(default=False)

    class Meta:
        verbose_name = 'User Profile'
        verbose_name_plural = 'User Profiles'

    def __str__(self):
        return f"{self.user.username}'s Profile"

    @property
    def full_name(self):
        return f"{self.user.first_name} {self.user.last_name}".strip()


class Wallet(TimeStampedModel):
    """User's digital wallet"""
    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name='wallet'
    )
    balance = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal('0.00'),
        validators=[MinValueValidator(Decimal('0.00'))]
    )
    currency = models.CharField(max_length=3, default='USD')
    is_active = models.BooleanField(default=True)
    daily_limit = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal('1000.00')
    )
    monthly_limit = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal('10000.00')
    )

    class Meta:
        verbose_name = 'Wallet'
        verbose_name_plural = 'Wallets'

    def __str__(self):
        return f"{self.user.username}'s Wallet - Balance: {self.currency} {self.balance}"

    def can_debit(self, amount):
        """Check if wallet has sufficient balance for debit"""
        return self.balance >= amount and self.is_active

    def debit(self, amount):
        """Debit amount from wallet"""
        if not self.can_debit(amount):
            raise ValidationError("Insufficient balance or inactive wallet")
        self.balance -= amount
        self.save()

    def credit(self, amount):
        """Credit amount to wallet"""
        if not self.is_active:
            raise ValidationError("Cannot credit to inactive wallet")
        self.balance += amount
        self.save()


class Card(TimeStampedModel):
    """User's payment cards"""
    CARD_TYPES = [
        ('visa', 'Visa'),
        ('mastercard', 'Mastercard'),
        ('amex', 'American Express'),
    ]

    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='cards'
    )
    card_number = models.CharField(
        max_length=16,
        validators=[RegexValidator(
            regex=r'^\d{16}$',
            message='Card number must be 16 digits'
        )]
    )
    card_type = models.CharField(max_length=10, choices=CARD_TYPES)
    card_holder_name = models.CharField(max_length=100)
    expiry_month = models.IntegerField(
        validators=[
            MinValueValidator(1),
            MaxValueValidator(12)
        ]
    )
    expiry_year = models.IntegerField(
        validators=[
            MinValueValidator(2024),
            MaxValueValidator(2050)
        ]
    )
    cvv = models.CharField(
        max_length=4,
        validators=[RegexValidator(
            regex=r'^\d{3,4}$',
            message='CVV must be 3 or 4 digits'
        )]
    )
    is_active = models.BooleanField(default=True)
    is_default = models.BooleanField(default=False)

    class Meta:
        verbose_name = 'Card'
        verbose_name_plural = 'Cards'
        unique_together = ['user', 'card_number']

    def __str__(self):
        return f"{self.card_type.title()} ending in {self.card_number[-4:]}"

    def clean(self):
        """Custom validation"""
        from datetime import datetime
        current_year = datetime.now().year
        current_month = datetime.now().month

        if self.expiry_year < current_year or (
                self.expiry_year == current_year and self.expiry_month < current_month
        ):
            raise ValidationError("Card has expired")

    def save(self, *args, **kwargs):
        self.full_clean()

        # Ensure only one default card per user
        if self.is_default:
            Card.objects.filter(user=self.user, is_default=True).update(is_default=False)

        super().save(*args, **kwargs)

    @property
    def masked_number(self):
        """Return masked card number for display"""
        return f"****-****-****-{self.card_number[-4:]}"


class Transaction(TimeStampedModel):
    """Transaction records"""
    TRANSACTION_TYPES = [
        ('card_to_wallet', 'Card to Wallet'),
        ('wallet_to_card', 'Wallet to Card'),
        ('wallet_to_bkash', 'Wallet to bKash'),
        ('wallet_to_nagad', 'Wallet to Nagad'),
        ('bkash_to_wallet', 'bKash to Wallet'),
        ('nagad_to_wallet', 'Nagad to Wallet'),
        ('wallet_to_wallet', 'Wallet to Wallet'),
    ]

    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('processing', 'Processing'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
        ('cancelled', 'Cancelled'),
    ]

    transaction_id = models.UUIDField(
        default=uuid.uuid4,
        editable=False,
        unique=True,
        db_index=True
    )
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='transactions'
    )
    transaction_type = models.CharField(max_length=20, choices=TRANSACTION_TYPES)
    amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(Decimal('0.01'))]
    )
    fee = models.DecimalField(
        max_digits=8,
        decimal_places=2,
        default=Decimal('0.00')
    )
    status = models.CharField(
        max_length=15,
        choices=STATUS_CHOICES,
        default='pending',
        db_index=True
    )

    # Related objects
    card = models.ForeignKey(
        Card,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='transactions'
    )
    recipient_user = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='received_transactions'
    )

    # Mobile payment details
    mobile_number = models.CharField(
        max_length=15,
        blank=True,
        validators=[RegexValidator(
            regex=r'^\+?1?\d{9,15}$',
            message="Enter a valid mobile number"
        )]
    )

    # Transaction details
    description = models.TextField(blank=True)
    reference_number = models.CharField(max_length=50, blank=True)

    # Timestamps
    completed_at = models.DateTimeField(null=True, blank=True)
    failed_at = models.DateTimeField(null=True, blank=True)

    # Metadata
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.TextField(blank=True)

    class Meta:
        verbose_name = 'Transaction'
        verbose_name_plural = 'Transactions'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['user', '-created_at']),
            models.Index(fields=['status', '-created_at']),
            models.Index(fields=['transaction_type', '-created_at']),
        ]

    def __str__(self):
        return f"{self.get_transaction_type_display()} - {self.amount} - {self.get_status_display()}"

    @property
    def total_amount(self):
        """Total amount including fees"""
        return self.amount + self.fee

    def can_cancel(self):
        """Check if transaction can be cancelled"""
        return self.status in ['pending', 'processing']

    def mark_completed(self):
        """Mark transaction as completed"""
        from django.utils import timezone
        self.status = 'completed'
        self.completed_at = timezone.now()
        self.save()

    def mark_failed(self, reason=None):
        """Mark transaction as failed"""
        from django.utils import timezone
        self.status = 'failed'
        self.failed_at = timezone.now()
        if reason:
            self.description = f"{self.description}\nFailure reason: {reason}"
        self.save()


class TransactionLog(TimeStampedModel):
    """Log of transaction status changes"""
    transaction = models.ForeignKey(
        Transaction,
        on_delete=models.CASCADE,
        related_name='logs'
    )
    previous_status = models.CharField(max_length=15)
    new_status = models.CharField(max_length=15)
    reason = models.TextField(blank=True)
    changed_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True
    )

    class Meta:
        verbose_name = 'Transaction Log'
        verbose_name_plural = 'Transaction Logs'
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.transaction.transaction_id} - {self.previous_status} to {self.new_status}"