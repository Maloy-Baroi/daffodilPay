# wallet/views.py
from rest_framework import serializers
from rest_framework import generics, status, permissions, filters
from rest_framework.response import Response
from rest_framework.authtoken.models import Token
from rest_framework.decorators import action
from rest_framework.viewsets import ModelViewSet, ReadOnlyModelViewSet
from django_filters.rest_framework import DjangoFilterBackend
from django.contrib.auth.models import User
from django.db import transaction
from django.utils import timezone
from decimal import Decimal
import logging

from .models import UserProfile, Wallet, Card, Transaction, TransactionLog
from .serializers import (
    UserRegistrationSerializer, UserLoginSerializer, UserProfileSerializer,
    WalletSerializer, CardSerializer, CardListSerializer, TransactionSerializer,
    TransferSerializer, TransactionLogSerializer
)
from .permissions import IsOwner, IsActiveUser, CanPerformTransaction
from utils.wallet_process import (
    TransactionProcessor, FeeCalculator, TransactionValidator,
    get_client_ip, mask_sensitive_data
)

logger = logging.getLogger(__name__)


class UserRegistrationView(generics.CreateAPIView):
    """User registration endpoint"""
    queryset = User.objects.all()
    serializer_class = UserRegistrationSerializer
    permission_classes = [permissions.AllowAny]

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        user = serializer.save()
        token, created = Token.objects.get_or_create(user=user)

        logger.info(f"New user registered: {user.username}")

        return Response({
            'token': token.key,
            'user_id': user.id,
            'username': user.username,
            'email': user.email,
            'message': 'User registered successfully'
        }, status=status.HTTP_201_CREATED)


class UserLoginView(generics.GenericAPIView):
    """User login endpoint"""
    serializer_class = UserLoginSerializer
    permission_classes = [permissions.AllowAny]

    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        user = serializer.validated_data['user']

        # Generate JWT tokens
        from rest_framework_simplejwt.tokens import RefreshToken
        refresh = RefreshToken.for_user(user)

        # Generate legacy token for backward compatibility
        token, created = Token.objects.get_or_create(user=user)

        # Update last login
        user.last_login = timezone.now()
        user.save(update_fields=['last_login'])

        logger.info(f"User logged in: {user.username}")

        return Response({
            'token': token.key,  # Legacy token
            'access': str(refresh.access_token),
            'refresh': str(refresh),
            'user_id': user.id,
            'username': user.username,
            'email': user.email,
            'message': 'Login successful'
        }, status=status.HTTP_200_OK)


class UserLogoutView(generics.GenericAPIView):
    """User logout endpoint"""
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = serializers.Serializer  # Empty serializer for swagger

    def post(self, request, *args, **kwargs):
        try:
            request.user.auth_token.delete()
            logger.info(f"User logged out: {request.user.username}")
            return Response(
                {'message': 'Logout successful'},
                status=status.HTTP_200_OK
            )
        except Exception as e:
            logger.error(f"Logout error for user {request.user.username}: {str(e)}")
            return Response(
                {'error': 'Error logging out'},
                status=status.HTTP_400_BAD_REQUEST
            )


class UserProfileView(generics.RetrieveUpdateAPIView):
    """User profile management"""
    serializer_class = UserProfileSerializer
    permission_classes = [permissions.IsAuthenticated, IsActiveUser]

    def get_object(self):
        profile, created = UserProfile.objects.get_or_create(user=self.request.user)
        return profile

    def update(self, request, *args, **kwargs):
        response = super().update(request, *args, **kwargs)
        logger.info(f"Profile updated for user: {request.user.username}")
        return response


class WalletView(generics.RetrieveUpdateAPIView):
    """Wallet management"""
    serializer_class = WalletSerializer
    permission_classes = [permissions.IsAuthenticated, IsActiveUser]

    def get_object(self):
        wallet, created = Wallet.objects.get_or_create(user=self.request.user)
        return wallet

    def update(self, request, *args, **kwargs):
        # Only allow updating certain fields
        partial = kwargs.pop('partial', False)
        instance = self.get_object()

        # Restrict which fields can be updated
        allowed_fields = ['daily_limit', 'monthly_limit']
        filtered_data = {
            key: value for key, value in request.data.items()
            if key in allowed_fields
        }

        serializer = self.get_serializer(instance, data=filtered_data, partial=partial)
        serializer.is_valid(raise_exception=True)
        self.perform_update(serializer)

        logger.info(f"Wallet updated for user: {request.user.username}")
        return Response(serializer.data)


class CardViewSet(ModelViewSet):
    """Card management viewset"""
    serializer_class = CardSerializer
    permission_classes = [permissions.IsAuthenticated, IsActiveUser, IsOwner]
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_fields = ['card_type', 'is_active', 'is_default']
    ordering_fields = ['created_at', 'card_type']
    ordering = ['-created_at']

    def get_queryset(self):
        if getattr(self, 'swagger_fake_view', False):  # swagger schema generation
            return Card.objects.none()
        return Card.objects.filter(user=self.request.user, is_active=True)

    def get_serializer_class(self):
        if self.action == 'list':
            return CardListSerializer
        return CardSerializer

    def perform_create(self, serializer):
        card = serializer.save(user=self.request.user)
        logger.info(f"New card added for user: {self.request.user.username}")

    def perform_destroy(self, instance):
        # Soft delete - mark as inactive
        instance.is_active = False
        instance.save()
        logger.info(f"Card deactivated for user: {self.request.user.username}")

    @action(detail=True, methods=['post'])
    def set_default(self, request, pk=None):
        """Set card as default"""
        card = self.get_object()

        # Remove default from other cards
        Card.objects.filter(user=request.user, is_default=True).update(is_default=False)

        # Set this card as default
        card.is_default = True
        card.save()

        logger.info(f"Default card set for user: {request.user.username}")
        return Response({'message': 'Card set as default'})


class TransactionViewSet(ReadOnlyModelViewSet):
    """Transaction history viewset"""
    serializer_class = TransactionSerializer
    permission_classes = [permissions.IsAuthenticated, IsActiveUser, IsOwner]
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_fields = ['transaction_type', 'status']
    ordering_fields = ['created_at', 'amount']
    ordering = ['-created_at']

    def get_queryset(self):
        if getattr(self, 'swagger_fake_view', False):  # swagger schema generation
            return Transaction.objects.none()
        return Transaction.objects.filter(user=self.request.user)

    @action(detail=True, methods=['post'])
    def cancel(self, request, pk=None):
        """Cancel a pending transaction"""
        transaction_obj = self.get_object()

        if not transaction_obj.can_cancel():
            return Response(
                {'error': 'Transaction cannot be cancelled'},
                status=status.HTTP_400_BAD_REQUEST
            )

        transaction_obj.status = 'cancelled'
        transaction_obj.save()

        # Log the cancellation
        TransactionLog.objects.create(
            transaction=transaction_obj,
            previous_status='pending',
            new_status='cancelled',
            reason='Cancelled by user',
            changed_by=request.user
        )

        logger.info(f"Transaction cancelled: {transaction_obj.transaction_id}")
        return Response({'message': 'Transaction cancelled successfully'})


class TransferMoneyView(generics.CreateAPIView):
    """Money transfer endpoint"""
    serializer_class = TransferSerializer
    permission_classes = [permissions.IsAuthenticated, IsActiveUser, CanPerformTransaction]

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        # Extract validated data
        transaction_type = serializer.validated_data['transaction_type']
        amount = serializer.validated_data['amount']
        card_id = serializer.validated_data.get('card_id')
        recipient_username = serializer.validated_data.get('recipient_username')
        mobile_number = serializer.validated_data.get('mobile_number')
        description = serializer.validated_data.get('description', '')

        try:
            with transaction.atomic():
                # Validate transaction limits
                TransactionValidator.validate_minimum_amount(amount)
                TransactionValidator.validate_maximum_amount(amount)
                TransactionValidator.validate_daily_limit(request.user, amount)
                TransactionValidator.validate_monthly_limit(request.user, amount)

                # Calculate fees
                fee = FeeCalculator.calculate_fee(transaction_type, amount)

                # Get related objects
                card = None
                recipient_user = None

                if card_id:
                    try:
                        card = Card.objects.get(id=card_id, user=request.user, is_active=True)
                    except Card.DoesNotExist:
                        return Response(
                            {'error': 'Card not found or inactive'},
                            status=status.HTTP_404_NOT_FOUND
                        )

                if recipient_username:
                    try:
                        recipient_user = User.objects.get(username=recipient_username)
                    except User.DoesNotExist:
                        return Response(
                            {'error': 'Recipient user not found'},
                            status=status.HTTP_404_NOT_FOUND
                        )

                # Create transaction record
                transaction_obj = Transaction.objects.create(
                    user=request.user,
                    transaction_type=transaction_type,
                    amount=amount,
                    fee=fee,
                    card=card,
                    recipient_user=recipient_user,
                    mobile_number=mobile_number,
                    description=description,
                    ip_address=get_client_ip(request),
                    user_agent=request.META.get('HTTP_USER_AGENT', '')[:500]
                )

                # Process the transaction
                processor = TransactionProcessor(request.user, transaction_obj)
                success, message = processor.process_transaction()

                if success:
                    # Log successful transaction
                    TransactionLog.objects.create(
                        transaction=transaction_obj,
                        previous_status='pending',
                        new_status='completed',
                        reason='Transaction processed successfully',
                        changed_by=request.user
                    )

                    logger.info(f"Transaction completed: {transaction_obj.transaction_id}")

                    return Response({
                        'transaction_id': str(transaction_obj.transaction_id),
                        'status': transaction_obj.status,
                        'amount': float(transaction_obj.amount),
                        'fee': float(transaction_obj.fee),
                        'total_amount': float(transaction_obj.total_amount),
                        'message': message,
                        'new_balance': float(request.user.wallet.balance)
                    }, status=status.HTTP_201_CREATED)

                else:
                    # Log failed transaction
                    TransactionLog.objects.create(
                        transaction=transaction_obj,
                        previous_status='pending',
                        new_status='failed',
                        reason=message,
                        changed_by=request.user
                    )

                    logger.warning(f"Transaction failed: {transaction_obj.transaction_id} - {message}")

                    return Response({
                        'transaction_id': str(transaction_obj.transaction_id),
                        'status': transaction_obj.status,
                        'message': message,
                        'balance': float(request.user.wallet.balance)
                    }, status=status.HTTP_400_BAD_REQUEST)

        except Exception as e:
            logger.error(f"Transaction error for user {request.user.username}: {str(e)}")
            return Response(
                {'error': f'Transaction failed: {str(e)}'},
                status=status.HTTP_400_BAD_REQUEST
            )


class TransactionLogView(generics.ListAPIView):
    """Transaction log history"""
    serializer_class = TransactionLogSerializer
    permission_classes = [permissions.IsAuthenticated, IsActiveUser]
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_fields = ['new_status', 'previous_status']
    ordering = ['-created_at']

    def get_queryset(self):
        return TransactionLog.objects.filter(
            transaction__user=self.request.user
        ).select_related('transaction', 'changed_by')


class DashboardView(generics.GenericAPIView):
    """Dashboard with summary statistics"""
    permission_classes = [permissions.IsAuthenticated, IsActiveUser]
    serializer_class = serializers.Serializer  # Empty serializer for swagger

    def get(self, request):
        user = request.user
        wallet = user.wallet

        # Get transaction statistics
        transactions = Transaction.objects.filter(user=user)

        # Recent transactions
        recent_transactions = transactions.order_by('-created_at')[:10]

        # Transaction summary
        from django.db.models import Sum, Count
        from datetime import datetime, timedelta

        today = timezone.now().date()
        this_month = timezone.now().replace(day=1, hour=0, minute=0, second=0, microsecond=0)

        summary = {
            'wallet_balance': float(wallet.balance),
            'wallet_currency': wallet.currency,
            'total_transactions': transactions.count(),
            'completed_transactions': transactions.filter(status='completed').count(),
            'pending_transactions': transactions.filter(status='pending').count(),
            'failed_transactions': transactions.filter(status='failed').count(),
            'today_transactions': transactions.filter(created_at__date=today).count(),
            'monthly_spent': float(
                transactions.filter(
                    created_at__gte=this_month,
                    status='completed',
                    transaction_type__in=['wallet_to_card', 'wallet_to_bkash', 'wallet_to_nagad', 'wallet_to_wallet']
                ).aggregate(total=Sum('amount'))['total'] or 0
            ),
            'monthly_received': float(
                transactions.filter(
                    created_at__gte=this_month,
                    status='completed',
                    transaction_type__in=['card_to_wallet', 'bkash_to_wallet', 'nagad_to_wallet']
                ).aggregate(total=Sum('amount'))['total'] or 0
            )
        }

        # Serialize recent transactions
        transaction_serializer = TransactionSerializer(recent_transactions, many=True)

        return Response({
            'summary': summary,
            'recent_transactions': transaction_serializer.data
        })