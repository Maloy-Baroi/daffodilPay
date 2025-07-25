# wallet/serializers.py
from rest_framework import serializers
from django.contrib.auth.models import User
from django.contrib.auth import authenticate
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from .models import UserProfile, Wallet, Card, Transaction, TransactionLog
from django.db import transaction


class UserRegistrationSerializer(serializers.ModelSerializer):
    """Serializer for user registration"""
    password = serializers.CharField(
        write_only=True,
        min_length=8,
        validators=[validate_password]
    )
    password_confirm = serializers.CharField(write_only=True)
    current_city = serializers.CharField(max_length=100)
    current_country = serializers.CharField(max_length=100)
    phone_number = serializers.CharField(max_length=15, required=False, allow_blank=True)

    class Meta:
        model = User
        fields = [
            'username', 'email', 'password', 'password_confirm',
            'first_name', 'last_name', 'current_city', 'current_country',
            'phone_number'
        ]
        extra_kwargs = {
            'email': {'required': True},
            'first_name': {'required': True},
            'last_name': {'required': True},
        }

    def validate(self, attrs):
        """Validate password confirmation"""
        if attrs['password'] != attrs['password_confirm']:
            raise serializers.ValidationError(
                {"password_confirm": "Password fields didn't match."}
            )
        return attrs

    def validate_email(self, value):
        """Validate email uniqueness"""
        if User.objects.filter(email=value).exists():
            raise serializers.ValidationError("User with this email already exists.")
        return value

    def create(self, validated_data):
        """Create user and related profile"""
        # Remove confirmation password and profile fields
        validated_data.pop('password_confirm')
        current_city = validated_data.pop('current_city')
        current_country = validated_data.pop('current_country')
        phone_number = validated_data.pop('phone_number', '')

        with transaction.atomic():
            # Create user
            user = User.objects.create_user(**validated_data)

            # Create user profile if it doesn't exist
            UserProfile.objects.get_or_create(
                user=user,
                defaults={
                    'current_city': current_city,
                    'current_country': current_country,
                    'phone_number': phone_number
                }
            )

            # Create wallet for user if it doesn't exist
            Wallet.objects.get_or_create(user=user)

            return user


class UserLoginSerializer(serializers.Serializer):
    """Serializer for user login"""
    username = serializers.CharField()
    password = serializers.CharField(write_only=True)

    def validate(self, attrs):
        """Validate user credentials"""
        username = attrs.get('username')
        password = attrs.get('password')

        if username and password:
            user = authenticate(username=username, password=password)
            if not user:
                raise serializers.ValidationError(
                    'Unable to log in with provided credentials.'
                )
            if not user.is_active:
                raise serializers.ValidationError(
                    'User account is disabled.'
                )
            attrs['user'] = user
        else:
            raise serializers.ValidationError(
                'Must include "username" and "password".'
            )

        return attrs


class UserProfileSerializer(serializers.ModelSerializer):
    """Serializer for user profile"""
    username = serializers.CharField(source='user.username', read_only=True)
    email = serializers.EmailField(source='user.email', read_only=True)
    first_name = serializers.CharField(source='user.first_name', read_only=True)
    last_name = serializers.CharField(source='user.last_name', read_only=True)
    full_name = serializers.ReadOnlyField()
    date_joined = serializers.DateTimeField(source='user.date_joined', read_only=True)

    class Meta:
        model = UserProfile
        fields = [
            'username', 'email', 'first_name', 'last_name', 'full_name',
            'current_city', 'current_country', 'phone_number', 'date_of_birth',
            'profile_picture', 'is_verified', 'date_joined', 'created_at', 'updated_at'
        ]
        read_only_fields = ['is_verified', 'created_at', 'updated_at']


class WalletSerializer(serializers.ModelSerializer):
    """Serializer for wallet"""
    username = serializers.CharField(source='user.username', read_only=True)

    class Meta:
        model = Wallet
        fields = [
            'username', 'balance', 'currency', 'is_active',
            'daily_limit', 'monthly_limit', 'created_at', 'updated_at'
        ]
        read_only_fields = ['balance', 'created_at', 'updated_at']


class CardSerializer(serializers.ModelSerializer):
    """Serializer for payment cards"""
    masked_number = serializers.ReadOnlyField()

    class Meta:
        model = Card
        fields = [
            'id', 'card_number', 'masked_number', 'card_type', 'card_holder_name',
            'expiry_month', 'expiry_year', 'cvv', 'is_active', 'is_default',
            'created_at'
        ]
        extra_kwargs = {
            'cvv': {'write_only': True},
            'card_number': {'write_only': True}
        }

    def validate_card_number(self, value):
        """Validate card number uniqueness for user"""
        user = self.context['request'].user
        if Card.objects.filter(user=user, card_number=value, is_active=True).exists():
            raise serializers.ValidationError("Card with this number already exists.")
        return value

    def create(self, validated_data):
        """Create card with user context"""
        validated_data['user'] = self.context['request'].user
        return super().create(validated_data)


class CardListSerializer(serializers.ModelSerializer):
    """Simplified serializer for card listing"""
    masked_number = serializers.ReadOnlyField()

    class Meta:
        model = Card
        fields = [
            'id', 'masked_number', 'card_type', 'card_holder_name',
            'expiry_month', 'expiry_year', 'is_default', 'created_at'
        ]


class TransactionSerializer(serializers.ModelSerializer):
    """Serializer for transactions"""
    username = serializers.CharField(source='user.username', read_only=True)
    card_info = CardListSerializer(source='card', read_only=True)
    recipient_username = serializers.CharField(source='recipient_user.username', read_only=True)
    total_amount = serializers.ReadOnlyField()
    transaction_type_display = serializers.CharField(
        source='get_transaction_type_display',
        read_only=True
    )
    status_display = serializers.CharField(source='get_status_display', read_only=True)

    class Meta:
        model = Transaction
        fields = [
            'transaction_id', 'username', 'transaction_type', 'transaction_type_display',
            'amount', 'fee', 'total_amount', 'status', 'status_display',
            'card', 'card_info', 'recipient_user', 'recipient_username',
            'mobile_number', 'description', 'reference_number',
            'created_at', 'completed_at', 'failed_at'
        ]
        read_only_fields = [
            'transaction_id', 'status', 'fee', 'created_at',
            'completed_at', 'failed_at'
        ]

    def create(self, validated_data):
        """Create transaction with user context"""
        validated_data['user'] = self.context['request'].user
        return super().create(validated_data)


class TransferSerializer(serializers.Serializer):
    """Serializer for money transfer requests"""
    transaction_type = serializers.ChoiceField(choices=Transaction.TRANSACTION_TYPES)
    amount = serializers.DecimalField(max_digits=12, decimal_places=2, min_value=0.01)
    card_id = serializers.IntegerField(required=False, allow_null=True)
    recipient_username = serializers.CharField(required=False, allow_blank=True)
    mobile_number = serializers.CharField(
        required=False,
        allow_blank=True,
        max_length=15
    )
    description = serializers.CharField(
        required=False,
        allow_blank=True,
        max_length=500
    )

    def validate(self, attrs):
        """Validate transfer data based on transaction type"""
        transaction_type = attrs.get('transaction_type')
        card_id = attrs.get('card_id')
        mobile_number = attrs.get('mobile_number')
        recipient_username = attrs.get('recipient_username')

        # Validate card-related transactions
        if transaction_type in ['card_to_wallet', 'wallet_to_card']:
            if not card_id:
                raise serializers.ValidationError(
                    {"card_id": "Card ID is required for card transactions."}
                )

        # Validate mobile payment transactions
        if transaction_type in ['wallet_to_bkash', 'wallet_to_nagad', 'bkash_to_wallet', 'nagad_to_wallet']:
            if not mobile_number:
                raise serializers.ValidationError(
                    {"mobile_number": "Mobile number is required for mobile payment transactions."}
                )

        # Validate wallet-to-wallet transactions
        if transaction_type == 'wallet_to_wallet':
            if not recipient_username:
                raise serializers.ValidationError(
                    {"recipient_username": "Recipient username is required for wallet transfers."}
                )

            # Check if recipient exists
            try:
                User.objects.get(username=recipient_username)
            except User.DoesNotExist:
                raise serializers.ValidationError(
                    {"recipient_username": "Recipient user does not exist."}
                )

        return attrs

    def validate_card_id(self, value):
        """Validate card belongs to user and is active"""
        if value:
            user = self.context['request'].user
            try:
                card = Card.objects.get(id=value, user=user, is_active=True)
            except Card.DoesNotExist:
                raise serializers.ValidationError("Card not found or inactive.")
        return value


class TransactionLogSerializer(serializers.ModelSerializer):
    """Serializer for transaction logs"""
    transaction_id = serializers.UUIDField(source='transaction.transaction_id', read_only=True)
    changed_by_username = serializers.CharField(source='changed_by.username', read_only=True)

    class Meta:
        model = TransactionLog
        fields = [
            'id', 'transaction_id', 'previous_status', 'new_status',
            'reason', 'changed_by_username', 'created_at'
        ]