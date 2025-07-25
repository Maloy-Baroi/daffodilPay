# wallet/signals.py
from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver
from django.contrib.auth.models import User
from .models import UserProfile, Wallet, Transaction, TransactionLog
import logging

logger = logging.getLogger(__name__)


@receiver(post_save, sender=User)
def create_user_profile_and_wallet(sender, instance, created, **kwargs):
    """Create UserProfile and Wallet when a new User is created"""
    if created:
        try:
            # Create UserProfile if it doesn't exist
            if not hasattr(instance, 'profile'):
                UserProfile.objects.create(
                    user=instance,
                    current_city='',
                    current_country=''
                )

            # Create Wallet if it doesn't exist
            if not hasattr(instance, 'wallet'):
                Wallet.objects.create(user=instance)

            logger.info(f"Profile and wallet created for user: {instance.username}")

        except Exception as e:
            logger.error(f"Error creating profile/wallet for user {instance.username}: {str(e)}")


@receiver(pre_save, sender=Transaction)
def log_transaction_status_change(sender, instance, **kwargs):
    """Log transaction status changes"""
    if instance.pk:  # Only for existing transactions
        try:
            old_instance = Transaction.objects.get(pk=instance.pk)
            if old_instance.status != instance.status:
                # Create transaction log
                TransactionLog.objects.create(
                    transaction=instance,
                    previous_status=old_instance.status,
                    new_status=instance.status,
                    reason=f'Status changed from {old_instance.status} to {instance.status}'
                )
                logger.info(
                    f"Transaction status changed: {instance.transaction_id} - {old_instance.status} to {instance.status}")
        except Transaction.DoesNotExist:
            pass
        except Exception as e:
            logger.error(f"Error logging transaction status change: {str(e)}")


@receiver(post_save, sender=Transaction)
def update_wallet_balance_on_completion(sender, instance, created, **kwargs):
    """Update wallet balance when transaction is completed (backup mechanism)"""
    if not created and instance.status == 'completed':
        try:
            # This is a backup mechanism in case the main transaction processing fails
            # In normal operation, the TransactionProcessor handles balance updates
            pass
        except Exception as e:
            logger.error(f"Error in wallet balance update signal: {str(e)}")