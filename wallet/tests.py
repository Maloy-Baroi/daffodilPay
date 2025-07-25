# wallet/tests.py
from django.test import TestCase
from django.contrib.auth.models import User
from django.urls import reverse
from rest_framework.test import APITestCase, APIClient
from rest_framework.authtoken.models import Token
from rest_framework import status
from decimal import Decimal
from .models import UserProfile, Wallet, Card, Transaction
from ..utils.wallet_process import FeeCalculator, TransactionValidator


class ModelTests(TestCase):
    """Test cases for models"""

    def setUp(self):
        self.user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpass123',
            first_name='Test',
            last_name='User'
        )

    def test_user_profile_creation(self):
        """Test UserProfile creation"""
        profile = UserProfile.objects.create(
            user=self.user,
            current_city='Dhaka',
            current_country='Bangladesh',
            phone_number='+8801234567890'
        )
        self.assertEqual(profile.user, self.user)
        self.assertEqual(profile.full_name, 'Test User')

    def test_wallet_creation(self):
        """Test Wallet creation"""
        wallet = Wallet.objects.create(user=self.user)
        self.assertEqual(wallet.user, self.user)
        self.assertEqual(wallet.balance, Decimal('0.00'))
        self.assertTrue(wallet.is_active)

    def test_wallet_operations(self):
        """Test wallet credit and debit operations"""
        wallet = Wallet.objects.create(user=self.user)

        # Test credit
        wallet.credit(Decimal('100.00'))
        self.assertEqual(wallet.balance, Decimal('100.00'))

        # Test debit
        wallet.debit(Decimal('50.00'))
        self.assertEqual(wallet.balance, Decimal('50.00'))

        # Test insufficient balance
        with self.assertRaises(Exception):
            wallet.debit(Decimal('100.00'))

    def test_card_creation(self):
        """Test Card creation"""
        card = Card.objects.create(
            user=self.user,
            card_number='1234567890123456',
            card_type='visa',
            card_holder_name='Test User',
            expiry_month=12,
            expiry_year=2025,
            cvv='123'
        )
        self.assertEqual(card.masked_number, '****-****-****-3456')
        self.assertTrue(card.is_active)

    def test_transaction_creation(self):
        """Test Transaction creation"""
        transaction = Transaction.objects.create(
            user=self.user,
            transaction_type='card_to_wallet',
            amount=Decimal('100.00'),
            fee=Decimal('2.00'),
            description='Test transaction'
        )
        self.assertEqual(transaction.user, self.user)
        self.assertEqual(transaction.total_amount, Decimal('102.00'))
        self.assertEqual(transaction.status, 'pending')


class UtilTests(TestCase):
    """Test cases for utility functions"""

    def test_fee_calculator(self):
        """Test fee calculation"""
        # Test card to wallet fee (2%)
        fee = FeeCalculator.calculate_fee('card_to_wallet', Decimal('100.00'))
        self.assertEqual(fee, Decimal('2.00'))

        # Test minimum fee
        fee = FeeCalculator.calculate_fee('card_to_wallet', Decimal('1.00'))
        self.assertEqual(fee, Decimal('0.10'))

        # Test maximum fee
        fee = FeeCalculator.calculate_fee('card_to_wallet', Decimal('10000.00'))
        self.assertEqual(fee, Decimal('50.00'))

    def test_transaction_validator(self):
        """Test transaction validation"""
        # Test minimum amount validation
        with self.assertRaises(Exception):
            TransactionValidator.validate_minimum_amount(Decimal('0.00'))

        # Test maximum amount validation
        with self.assertRaises(Exception):
            TransactionValidator.validate_maximum_amount(Decimal('20000.00'))


class APITests(APITestCase):
    """Test cases for API endpoints"""

    def setUp(self):
        self.client = APIClient()
        self.user_data = {
            'username': 'testuser',
            'email': 'test@example.com',
            'password': 'testpass123',
            'password_confirm': 'testpass123',
            'first_name': 'Test',
            'last_name': 'User',
            'current_city': 'Dhaka',
            'current_country': 'Bangladesh'
        }

    def test_user_registration(self):
        """Test user registration endpoint"""
        url = reverse('wallet:register')
        response = self.client.post(url, self.user_data, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertIn('token', response.data)
        self.assertIn('username', response.data)

    def test_user_login(self):
        """Test user login endpoint"""
        # Create user first
        user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpass123'
        )

        url = reverse('wallet:login')
        login_data = {
            'username': 'testuser',
            'password': 'testpass123'
        }
        response = self.client.post(url, login_data, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('token', response.data)

    def test_protected_endpoint_without_token(self):
        """Test accessing protected endpoint without token"""
        url = reverse('wallet:wallet')
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_wallet_access_with_token(self):
        """Test accessing wallet with valid token"""
        # Create user and token
        user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpass123'
        )
        token = Token.objects.create(user=user)

        # Set authentication
        self.client.credentials(HTTP_AUTHORIZATION='Token ' + token.key)

        url = reverse('wallet:wallet')
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('balance', response.data)

    def test_card_creation(self):
        """Test card creation endpoint"""
        # Create user and authenticate
        user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpass123'
        )
        token = Token.objects.create(user=user)
        self.client.credentials(HTTP_AUTHORIZATION='Token ' + token.key)

        url = reverse('wallet:cards-list')
        card_data = {
            'card_number': '1234567890123456',
            'card_type': 'visa',
            'card_holder_name': 'Test User',
            'expiry_month': 12,
            'expiry_year': 2025,
            'cvv': '123'
        }
        response = self.client.post(url, card_data, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertIn('masked_number', response.data)

    def test_money_transfer(self):
        """Test money transfer endpoint"""
        # Create user and authenticate
        user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpass123'
        )
        token = Token.objects.create(user=user)
        self.client.credentials(HTTP_AUTHORIZATION='Token ' + token.key)

        # Create a card
        card = Card.objects.create(
            user=user,
            card_number='1234567890123456',
            card_type='visa',
            card_holder_name='Test User',
            expiry_month=12,
            expiry_year=2025,
            cvv='123'
        )

        url = reverse('wallet:transfer')
        transfer_data = {
            'transaction_type': 'card_to_wallet',
            'amount': '100.00',
            'card_id': card.id,
            'description': 'Test transfer'
        }
        response = self.client.post(url, transfer_data, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertIn('transaction_id', response.data)

    def test_dashboard_access(self):
        """Test dashboard endpoint"""
        # Create user and authenticate
        user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpass123'
        )
        token = Token.objects.create(user=user)
        self.client.credentials(HTTP_AUTHORIZATION='Token ' + token.key)

        url = reverse('wallet:dashboard')
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('summary', response.data)
        self.assertIn('recent_transactions', response.data)


class IntegrationTests(APITestCase):
    """Integration tests for complete workflows"""

    def setUp(self):
        self.client = APIClient()

    def test_complete_user_workflow(self):
        """Test complete user workflow from registration to transaction"""
        # 1. Register user
        register_url = reverse('wallet:register')
        user_data = {
            'username': 'testuser',
            'email': 'test@example.com',
            'password': 'testpass123',
            'password_confirm': 'testpass123',
            'first_name': 'Test',
            'last_name': 'User',
            'current_city': 'Dhaka',
            'current_country': 'Bangladesh'
        }
        response = self.client.post(register_url, user_data, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        token = response.data['token']

        # 2. Set authentication
        self.client.credentials(HTTP_AUTHORIZATION='Token ' + token)

        # 3. Check wallet
        wallet_url = reverse('wallet:wallet')
        response = self.client.get(wallet_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['balance'], '0.00')

        # 4. Add card
        cards_url = reverse('wallet:cards-list')
        card_data = {
            'card_number': '1234567890123456',
            'card_type': 'visa',
            'card_holder_name': 'Test User',
            'expiry_month': 12,
            'expiry_year': 2025,
            'cvv': '123'
        }
        response = self.client.post(cards_url, card_data, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        card_id = response.data['id']

        # 5. Transfer money to wallet
        transfer_url = reverse('wallet:transfer')
        transfer_data = {
            'transaction_type': 'card_to_wallet',
            'amount': '100.00',
            'card_id': card_id,
            'description': 'Adding funds'
        }
        response = self.client.post(transfer_url, transfer_data, format='json')
        # Transaction might succeed or fail based on simulation
        self.assertIn(response.status_code, [status.HTTP_201_CREATED, status.HTTP_400_BAD_REQUEST])

        # 6. Check transaction history
        transactions_url = reverse('wallet:transactions-list')
        response = self.client.get(transactions_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertGreater(len(response.data['results']), 0)

        # 7. Access dashboard
        dashboard_url = reverse('wallet:dashboard')
        response = self.client.get(dashboard_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('summary', response.data)
