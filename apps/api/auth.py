"""
JWT Authentication for Django Ninja.
"""
import logging
from typing import Any, Optional

from ninja.security import HttpBearer
from rest_framework_simplejwt.tokens import AccessToken
from rest_framework_simplejwt.exceptions import TokenError, InvalidToken
from django.contrib.auth import get_user_model
from django.http import HttpRequest

logger = logging.getLogger(__name__)
User = get_user_model()


class JWTAuth(HttpBearer):
    """
    JWT Authentication class for Django Ninja.
    Validates Bearer tokens and returns the authenticated user.
    """

    def authenticate(self, request: HttpRequest, token: str) -> Optional[Any]:
        """
        Validate the JWT token and return the user.

        Args:
            request: The HTTP request
            token: The JWT token from Authorization header

        Returns:
            User object if valid, None otherwise
        """
        try:
            # Decode and validate token
            access_token = AccessToken(token)

            # Get user ID from token
            user_id = access_token.get('user_id')

            if not user_id:
                return None

            # Get user from database
            user = User.objects.get(id=user_id)

            if not user.is_active:
                return None

            return user

        except TokenError:
            return None
        except InvalidToken:
            return None
        except User.DoesNotExist:
            return None
        except (ValueError, KeyError, AttributeError) as e:
            logger.warning(f"JWT authentication error: {e}")
            return None


class OptionalJWTAuth(JWTAuth):
    """
    Optional JWT Authentication.
    Returns None instead of raising error if no token provided.
    """

    def authenticate(self, request: HttpRequest, token: Optional[str] = None) -> Optional[Any]:
        if not token:
            return None
        return super().authenticate(request, token)
