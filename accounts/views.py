from __future__ import annotations

from django.contrib.auth import authenticate, login as dj_login, logout as dj_logout
from django.middleware.csrf import get_token
from django.utils.translation import gettext_lazy as _
from rest_framework import status, permissions, serializers
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView
from drf_spectacular.utils import extend_schema, OpenApiResponse


class _UserPublicSerializer(serializers.Serializer):
    """Minimal public shape for the authenticated user."""
    id = serializers.IntegerField()
    username = serializers.CharField()
    email = serializers.EmailField(allow_blank=True)


class _LoginSerializer(serializers.Serializer):
    username = serializers.CharField()
    password = serializers.CharField(write_only=True, trim_whitespace=False)


class CsrfView(APIView):
    """
    GET only: prime a CSRF cookie and expose the token.

    - Sets the `csrftoken` cookie (via `get_token(request)`).
    - Returns HTTP 204 with **no body** for stability, but includes the token in
      the `X-CSRFToken` response header so SPAs can read it even if
      `CSRF_COOKIE_HTTPONLY=True` in production.
    """
    permission_classes = [permissions.AllowAny]

    @extend_schema(
        operation_id="auth_csrf",
        summary="Prime CSRF cookie",
        description=(
            "Generates/sets the CSRF cookie and returns 204. The CSRF token is "
            "also provided in the `X-CSRFToken` response header for SPA clients."
        ),
        responses={204: OpenApiResponse(description="CSRF cookie set")},
    )
    def get(self, request, *args, **kwargs):
        token = get_token(request)  # ensures cookie is set
        resp = Response(status=status.HTTP_204_NO_CONTENT)
        resp["X-CSRFToken"] = token
        return resp


class LoginView(APIView):
    """
    Session login using Django auth.
    - Throttled with scope `auth-login`.
    - Returns 200 with minimal user JSON, or 400 on invalid credentials.
    """
    permission_classes = [permissions.AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "auth-login"

    @extend_schema(
        operation_id="auth_login",
        summary="Log in (session-based)",
        request=_LoginSerializer,
        responses={
            200: _UserPublicSerializer,
            400: OpenApiResponse(
                description='{"detail":"Invalid username or password.","code":"invalid_credentials"}'
            ),
            429: OpenApiResponse(description="Too many attempts (throttled)"),
        },
    )
    def post(self, request, *args, **kwargs):
        data = _LoginSerializer(data=request.data)
        data.is_valid(raise_exception=False)
        if not data.is_valid():
            return Response(
                {"detail": _("Invalid username or password."), "code": "invalid_credentials"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        user = authenticate(request, username=data.validated_data["username"],
                            password=data.validated_data["password"])
        if user is None or not user.is_active:
            return Response(
                {"detail": _("Invalid username or password."), "code": "invalid_credentials"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        dj_login(request, user)
        payload = {"id": user.id, "username": user.get_username(), "email": user.email or ""}
        return Response(payload, status=status.HTTP_200_OK)


class LogoutView(APIView):
    """
    Session logout.
    - Returns 204 even if the user is already logged out (idempotent).
    - CSRF is enforced by middleware (do NOT exempt).
    """
    permission_classes = [permissions.AllowAny]

    @extend_schema(
        operation_id="auth_logout",
        summary="Log out",
        responses={204: OpenApiResponse(description="Logged out")},
    )
    def post(self, request, *args, **kwargs):
        dj_logout(request)
        return Response(status=status.HTTP_204_NO_CONTENT)


class MeView(APIView):
    """
    Return the current authenticated user or 401 if not logged in.
    """
    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(
        operation_id="auth_me",
        summary="Current user",
        responses={
            200: _UserPublicSerializer,
            401: OpenApiResponse(description="Not authenticated"),
        },
    )
    def get(self, request, *args, **kwargs):
        u = request.user
        payload = {"id": u.id, "username": u.get_username(), "email": u.email or ""}
        return Response(payload, status=status.HTTP_200_OK)
