"""
Main API router configuration.
"""
from typing import Any

from ninja import NinjaAPI
from ninja.errors import ValidationError, HttpError
from django.http import Http404, HttpRequest, HttpResponse
from .auth import JWTAuth

# Create main API instance
api = NinjaAPI(
    title="TransMaint API",
    version="1.0.0",
    description="""
    API para la aplicación móvil TransMaint.

    ## Autenticación
    La API usa JWT (JSON Web Tokens) para autenticación.
    Obtén un token en `/api/auth/login` y úsalo en el header:
    `Authorization: Bearer <token>`

    ## Endpoints principales
    - `/auth/` - Autenticación y gestión de usuarios
    - `/actividades/` - Actividades programadas
    - `/campo/` - Registros de campo y evidencias
    - `/lineas/` - Líneas y torres
    - `/cuadrillas/` - Cuadrillas y ubicaciones
    """,
    auth=JWTAuth(),
    docs_url="/docs",
)


# Exception handlers
@api.exception_handler(ValidationError)
def validation_error_handler(request: HttpRequest, exc: ValidationError) -> HttpResponse:
    return api.create_response(
        request,
        {"detail": exc.errors},
        status=422
    )


@api.exception_handler(Http404)
def not_found_handler(request: HttpRequest, exc: Http404) -> HttpResponse:
    return api.create_response(
        request,
        {"detail": "Recurso no encontrado"},
        status=404
    )


@api.exception_handler(HttpError)
def http_error_handler(request: HttpRequest, exc: HttpError) -> HttpResponse:
    return api.create_response(
        request,
        {"detail": str(exc.message)},
        status=exc.status_code
    )


# Health check (no auth required)
@api.get("/health", auth=None, tags=["System"])
def health_check(request: HttpRequest) -> dict[str, str]:
    """Health check endpoint."""
    return {"status": "healthy", "service": "transmaint-api"}


# Register routers from each app
from apps.usuarios.api import router as usuarios_router
from apps.lineas.api import router as lineas_router
from apps.cuadrillas.api import router as cuadrillas_router
from apps.actividades.api import router as actividades_router
from apps.campo.api import router as campo_router

api.add_router("/auth/", usuarios_router, tags=["Autenticación"])
api.add_router("/lineas/", lineas_router, tags=["Líneas y Torres"])
api.add_router("/cuadrillas/", cuadrillas_router, tags=["Cuadrillas"])
api.add_router("/actividades/", actividades_router, tags=["Actividades"])
api.add_router("/campo/", campo_router, tags=["Campo"])
