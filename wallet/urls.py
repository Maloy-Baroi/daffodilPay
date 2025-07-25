# wallet/urls.py
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from rest_framework_simplejwt.views import TokenRefreshView, TokenVerifyView
from . import views

# Create router for viewsets
router = DefaultRouter()
router.register(r'cards', views.CardViewSet, basename='cards')
router.register(r'transactions', views.TransactionViewSet, basename='transactions')

app_name = 'wallet'

urlpatterns = [
    # Authentication endpoints
    path('auth/register/', views.UserRegistrationView.as_view(), name='register'),
    path('auth/login/', views.UserLoginView.as_view(), name='login'),
    path('auth/logout/', views.UserLogoutView.as_view(), name='logout'),
    path('auth/token/refresh/', TokenRefreshView.as_view(), name='token-refresh'),
    path('auth/token/verify/', TokenVerifyView.as_view(), name='token-verify'),

    # User profile
    path('profile/', views.UserProfileView.as_view(), name='profile'),

    # Wallet management
    path('wallet/', views.WalletView.as_view(), name='wallet'),

    # Money transfer
    path('transfer/', views.TransferMoneyView.as_view(), name='transfer'),

    # Transaction logs
    path('transaction-logs/', views.TransactionLogView.as_view(), name='transaction-logs'),

    # Dashboard
    path('dashboard/', views.DashboardView.as_view(), name='dashboard'),

    # Include router URLs
    path('', include(router.urls)),
]