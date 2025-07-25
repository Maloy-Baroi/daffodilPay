# wallet/utils.py
from decimal import Decimal
from django.utils import timezone
from django.core.exceptions import ValidationError
from django.db import transaction
import random
import logging

logger = logging.getLogger(__name__)


class TransactionProcessor:
    """Utility class for processing different types of transactions"""

    def __init__(self, user, transaction_obj):
        self.user = user
        self.transaction = transaction_obj
        self.wallet = user.wallet

    def process_transaction(self):
        """Process transaction based on type"""
        transaction_type = self.transaction.transaction_type

        try:
            with transaction.atomic():
                if transaction_type == 'card_to_wallet':
                    return self._process_card_to_wallet()
                elif transaction_type == 'wallet_to_card':
                    return self._process_wallet_to_card()
                elif transaction_type in ['wallet_to_bkash', 'wallet_to_nagad']:
                    return self._process_wallet_to_mobile()
                elif transaction_type in ['bkash_to_wallet', 'nagad_to_wallet']:
                    return self._process_mobile_to_wallet()
                elif transaction_type == 'wallet_to_wallet':
                    return self._process_wallet_to_wallet()
                else:
                    raise ValidationError("Invalid transaction type")

        except Exception as e:
            logger.error(f"Transaction processing failed: {str(e)}")
            self.transaction.mark_failed(str(e))
            return False, str(e)

    def _process_card_to_wallet(self):
        """Process card to wallet transaction"""
        if not self.transaction.card:
            raise ValidationError("Card information required")

        # Simulate card verification and processing
        if self._simulate_card_processing():
            self.wallet.credit(self.transaction.amount)
            self.transaction.mark_completed()
            logger.info(f"Card to wallet transaction completed: {self.transaction.transaction_id}")
            return True, "Transaction completed successfully"
        else:
            raise ValidationError("Card processing failed")

    def _process_wallet_to_card(self):
        """Process wallet to card transaction"""
        if not self.transaction.card:
            raise ValidationError("Card information required")

        if not self.wallet.can_debit(self.transaction.total_amount):
            raise ValidationError("Insufficient wallet balance")

        # Simulate card processing
        if self._simulate_card_processing():
            self.wallet.debit(self.transaction.total_amount)
            self.transaction.mark_completed()
            logger.info(f"Wallet to card transaction completed: {self.transaction.transaction_id}")
            return True, "Transaction completed successfully"
        else:
            raise ValidationError("Card processing failed")

    def _process_wallet_to_mobile(self):
        """Process wallet to mobile payment transaction"""
        if not self.transaction.mobile_number:
            raise ValidationError("Mobile number required")

        if not self.wallet.can_debit(self.transaction.total_amount):
            raise ValidationError("Insufficient wallet balance")

        # Simulate mobile payment processing
        if self._simulate_mobile_processing():
            self.wallet.debit(self.transaction.total_amount)
            self.transaction.mark_completed()
            logger.info(f"Wallet to mobile transaction completed: {self.transaction.transaction_id}")
            return True, "Transaction completed successfully"
        else:
            raise ValidationError("Mobile payment processing failed")

    def _process_mobile_to_wallet(self):
        """Process mobile payment to wallet transaction"""
        if not self.transaction.mobile_number:
            raise ValidationError("Mobile number required")

        # Simulate mobile payment processing
        if self._simulate_mobile_processing():
            self.wallet.credit(self.transaction.amount)
            self.transaction.mark_completed()
            logger.info(f"Mobile to wallet transaction completed: {self.transaction.transaction_id}")
            return True, "Transaction completed successfully"
        else:
            raise ValidationError("Mobile payment processing failed")

    def _process_wallet_to_wallet(self):
        """Process wallet to wallet transaction"""
        if not self.transaction.recipient_user:
            raise ValidationError("Recipient user required")

        if not self.wallet.can_debit(self.transaction.total_amount):
            raise ValidationError("Insufficient wallet balance")

        try:
            recipient_wallet = self.transaction.recipient_user.wallet
            if not recipient_wallet.is_active:
                raise ValidationError("Recipient wallet is inactive")

            # Transfer money
            self.wallet.debit(self.transaction.total_amount)
            recipient_wallet.credit(self.transaction.amount)

            self.transaction.mark_completed()
            logger.info(f"Wallet to wallet transaction completed: {self.transaction.transaction_id}")
            return True, "Transaction completed successfully"

        except Exception as e:
            raise ValidationError(f"Wallet transfer failed: {str(e)}")

    def _simulate_card_processing(self):
        """Simulate card processing with 95% success rate"""
        return random.random() < 0.95

    def _simulate_mobile_processing(self):
        """Simulate mobile payment processing with 90% success rate"""
        return random.random() < 0.90


class FeeCalculator:
    """Utility class for calculating transaction fees"""

    # Fee structure (percentage of transaction amount)
    FEE_STRUCTURE = {
        'card_to_wallet': Decimal('0.02'),  # 2%
        'wallet_to_card': Decimal('0.015'),  # 1.5%
        'wallet_to_bkash': Decimal('0.01'),  # 1%
        'wallet_to_nagad': Decimal('0.01'),  # 1%
        'bkash_to_wallet': Decimal('0.005'),  # 0.5%
        'nagad_to_wallet': Decimal('0.005'),  # 0.5%
        'wallet_to_wallet': Decimal('0.001'),  # 0.1%
    }

    # Minimum and maximum fees
    MIN_FEE = Decimal('0.10')
    MAX_FEE = Decimal('50.00')

    @classmethod
    def calculate_fee(cls, transaction_type, amount):
        """Calculate transaction fee"""
        if transaction_type not in cls.FEE_STRUCTURE:
            return Decimal('0.00')

        fee_rate = cls.FEE_STRUCTURE[transaction_type]
        calculated_fee = amount * fee_rate

        # Apply minimum and maximum limits
        if calculated_fee < cls.MIN_FEE:
            return cls.MIN_FEE
        elif calculated_fee > cls.MAX_FEE:
            return cls.MAX_FEE

        return calculated_fee.quantize(Decimal('0.01'))


class TransactionValidator:
    """Utility class for validating transactions"""

    @staticmethod
    def validate_daily_limit(user, amount):
        """Check if transaction exceeds daily limit"""
        from ..wallet.models import Transaction
        from datetime import datetime, timedelta

        today = timezone.now().date()
        daily_total = Transaction.objects.filter(
            user=user,
            status='completed',
            created_at__date=today
        ).aggregate(
            total=models.Sum('amount')
        )['total'] or Decimal('0.00')

        wallet = user.wallet
        if daily_total + amount > wallet.daily_limit:
            raise ValidationError(
                f"Transaction exceeds daily limit of {wallet.currency} {wallet.daily_limit}"
            )

    @staticmethod
    def validate_monthly_limit(user, amount):
        """Check if transaction exceeds monthly limit"""
        from ..wallet.models import Transaction
        from datetime import datetime

        current_month = timezone.now().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        monthly_total = Transaction.objects.filter(
            user=user,
            status='completed',
            created_at__gte=current_month
        ).aggregate(
            total=models.Sum('amount')
        )['total'] or Decimal('0.00')

        wallet = user.wallet
        if monthly_total + amount > wallet.monthly_limit:
            raise ValidationError(
                f"Transaction exceeds monthly limit of {wallet.currency} {wallet.monthly_limit}"
            )

    @staticmethod
    def validate_minimum_amount(amount):
        """Validate minimum transaction amount"""
        min_amount = Decimal('0.01')
        if amount < min_amount:
            raise ValidationError(f"Minimum transaction amount is {min_amount}")

    @staticmethod
    def validate_maximum_amount(amount):
        """Validate maximum transaction amount"""
        max_amount = Decimal('10000.00')
        if amount > max_amount:
            raise ValidationError(f"Maximum transaction amount is {max_amount}")


def get_client_ip(request):
    """Get client IP address from request"""
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        ip = x_forwarded_for.split(',')[0]
    else:
        ip = request.META.get('REMOTE_ADDR')
    return ip


def mask_sensitive_data(data, field_name):
    """Mask sensitive data for logging"""
    if field_name == 'card_number':
        return f"****-****-****-{data[-4:]}" if len(data) >= 4 else "****"
    elif field_name == 'mobile_number':
        return f"***-***-{data[-4:]}" if len(data) >= 4 else "***"
    elif field_name == 'cvv':
        return "***"
    else:
        return data