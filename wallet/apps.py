# wallet/apps.py
from django.apps import AppConfig


class WalletConfig(AppConfig):
    """Wallet application configuration"""
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'wallet'
    verbose_name = 'Digital Wallet'

    def ready(self):
        """Import signals when app is ready"""
        import wallet.signals