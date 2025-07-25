# wallet/permissions.py
from rest_framework import permissions


class IsOwnerOrReadOnly(permissions.BasePermission):
    """
    Custom permission to only allow owners of an object to edit it.
    """

    def has_object_permission(self, request, view, obj):
        # Read permissions are allowed for any request,
        # so we'll always allow GET, HEAD or OPTIONS requests.
        if request.method in permissions.SAFE_METHODS:
            return True

        # Write permissions are only allowed to the owner of the object.
        return obj.user == request.user


class IsOwner(permissions.BasePermission):
    """
    Custom permission to only allow owners of an object to access it.
    """

    def has_object_permission(self, request, view, obj):
        # All permissions are only allowed to the owner of the object.
        return obj.user == request.user


class IsActiveUser(permissions.BasePermission):
    """
    Custom permission to only allow active users.
    """

    def has_permission(self, request, view):
        return request.user and request.user.is_authenticated and request.user.is_active


class IsVerifiedUser(permissions.BasePermission):
    """
    Custom permission to only allow verified users for sensitive operations.
    """

    def has_permission(self, request, view):
        if not (request.user and request.user.is_authenticated):
            return False

        # Check if user has a profile and is verified
        try:
            profile = request.user.profile
            return profile.is_verified
        except:
            return False


class CanPerformTransaction(permissions.BasePermission):
    """
    Custom permission for transaction operations.
    """

    def has_permission(self, request, view):
        if not (request.user and request.user.is_authenticated and request.user.is_active):
            return False

        # Check if user has an active wallet
        try:
            wallet = request.user.wallet
            return wallet.is_active
        except:
            return False