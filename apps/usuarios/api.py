"""
User API endpoints (Django Ninja).
"""
import logging
from typing import Any, Optional, Union
from uuid import UUID

from ninja import Router, Schema
from ninja.security import HttpBearer
from django.contrib.auth import authenticate
from django.http import HttpRequest
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.exceptions import TokenError, InvalidToken

from apps.api.auth import JWTAuth
from apps.api.ratelimit import ratelimit_login, ratelimit_api

logger = logging.getLogger(__name__)
router = Router(auth=JWTAuth())


class LoginIn(Schema):
    email: str
    password: str


class TokenOut(Schema):
    access: str
    refresh: str
    user_id: UUID
    email: str
    nombre: str
    rol: str


class UserOut(Schema):
    id: UUID
    email: str
    first_name: str
    last_name: str
    rol: str
    telefono: Optional[str]


class ErrorOut(Schema):
    detail: str


@router.post('/login', response={200: TokenOut, 401: ErrorOut, 429: ErrorOut}, auth=None)
@ratelimit_login
def login(request: HttpRequest, data: LoginIn) -> Union[dict[str, Any], tuple[int, dict[str, str]]]:
    """
    Authenticate user and return JWT tokens.

    Rate limited: 5 requests per minute per IP address.
    """
    user = authenticate(request, email=data.email, password=data.password)

    if user is None:
        return 401, {'detail': 'Credenciales inválidas'}

    if not user.is_active:
        return 401, {'detail': 'Usuario inactivo'}

    refresh = RefreshToken.for_user(user)

    return {
        'access': str(refresh.access_token),
        'refresh': str(refresh),
        'user_id': user.id,
        'email': user.email,
        'nombre': user.get_full_name(),
        'rol': user.rol,
    }


@router.post('/refresh', response={200: dict, 401: ErrorOut, 429: ErrorOut}, auth=None)
@ratelimit_login
def refresh_token(request: HttpRequest, refresh: str) -> Union[dict[str, str], tuple[int, dict[str, str]]]:
    """
    Refresh access token.

    Rate limited: 5 requests per minute per IP address.
    """
    try:
        token = RefreshToken(refresh)
        return {
            'access': str(token.access_token),
            'refresh': str(token),
        }
    except (TokenError, InvalidToken) as e:
        logger.warning(f"Token refresh failed: {e}")
        return 401, {'detail': 'Token invalido o expirado'}


@router.get('/me', response={200: UserOut, 429: ErrorOut})
@ratelimit_api
def get_current_user(request: HttpRequest) -> Any:
    """
    Get current authenticated user.

    Rate limited: 100 requests per minute per user.
    """
    user = request.auth
    return user
