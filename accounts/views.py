from __future__ import annotations

from django.conf import settings
from django.contrib.auth import (
    authenticate,
    get_user_model,
    login as dj_login,
    logout as dj_logout,
    update_session_auth_hash,
)
from django.contrib.auth.password_validation import validate_password
from django.middleware.csrf import get_token
from django.utils.translation import gettext_lazy as _
from rest_framework import permissions, serializers, status
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.validators import UniqueValidator
from rest_framework.views import APIView
from drf_spectacular.utils import extend_schema, OpenApiResponse

User = get_user_model()


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
    GET only: prime a CSRF cookie and expose the token via header.
    Returns 204 with no body.
    """
    permission_classes = [permissions.AllowAny]

    @extend_schema(
        operation_id="auth_csrf",
        summary="Prime CSRF cookie",
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
    Throttled with scope `auth-login`.
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
        ser = _LoginSerializer(data=request.data)
        if not ser.is_valid():
            return Response(
                {"detail": _("Invalid username or password."), "code": "invalid_credentials"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        user = authenticate(
            request,
            username=ser.validated_data["username"],
            password=ser.validated_data["password"],
        )
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
    Session logout (idempotent). CSRF enforced by middleware.
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
    Return the current authenticated user.
    """
    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(
        operation_id="auth_me",
        summary="Current user",
        responses={200: _UserPublicSerializer, 401: OpenApiResponse(description="Not authenticated")},
    )
    def get(self, request, *args, **kwargs):
        # Explicit 401 for clarity if something bypasses DRF's default handling.
        if not request.user.is_authenticated:
            return Response({"detail": _("Not authenticated.")}, status=status.HTTP_401_UNAUTHORIZED)
        u = request.user
        payload = {"id": u.id, "username": u.get_username(), "email": u.email or ""}
        return Response(payload, status=status.HTTP_200_OK)


# -----------------------------
# Registration
# -----------------------------
class _RegisterSerializer(serializers.Serializer):
    username = serializers.CharField(
        max_length=150,
        validators=[UniqueValidator(queryset=User.objects.all(), message=_("A user with that username already exists."))],
    )
    email = serializers.EmailField(
        validators=[UniqueValidator(queryset=User.objects.all(), message=_("A user with that email already exists."))],
    )
    password1 = serializers.CharField(write_only=True, trim_whitespace=False)
    password2 = serializers.CharField(write_only=True, trim_whitespace=False)

    def validate(self, attrs):
        p1 = attrs.get("password1")
        p2 = attrs.get("password2")
        if p1 != p2:
            raise serializers.ValidationError({"password2": _("Passwords do not match.")})
        validate_password(p1)
        return attrs

    def create(self, validated_data):
        return User.objects.create_user(
            username=validated_data["username"],
            email=validated_data["email"],
            password=validated_data["password1"],
        )


class RegisterView(APIView):
    """
    Create a new user account.
    - Requires email; validates strong password.
    - Throttled with scope `auth-register`.
    - Auto-logs in on success.
    - Controlled by `ENABLE_REGISTRATION`.
    """
    permission_classes = [permissions.AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "auth-register"

    @extend_schema(
        operation_id="auth_register",
        summary="Register a new account",
        request=_RegisterSerializer,
        responses={
            201: _UserPublicSerializer,
            400: OpenApiResponse(description="Validation error"),
            403: OpenApiResponse(description="Registration disabled"),
            429: OpenApiResponse(description="Too many attempts (throttled)"),
        },
    )
    def post(self, request, *args, **kwargs):
        if not getattr(settings, "ENABLE_REGISTRATION", False):
            return Response(
                {"detail": _("Registration is disabled."), "code": "registration_disabled"},
                status=status.HTTP_403_FORBIDDEN,
            )

        ser = _RegisterSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        user = ser.save()
        dj_login(request, user)

        payload = {"id": user.id, "username": user.get_username(), "email": user.email or ""}
        return Response(payload, status=status.HTTP_201_CREATED)


# -----------------------------
# Password Change (authenticated)
# -----------------------------
class _PasswordChangeSerializer(serializers.Serializer):
    old_password = serializers.CharField(write_only=True, trim_whitespace=False)
    new_password1 = serializers.CharField(write_only=True, trim_whitespace=False)
    new_password2 = serializers.CharField(write_only=True, trim_whitespace=False)

    def validate(self, attrs):
        request = self.context["request"]
        user = request.user
        if not user or not user.is_authenticated:
            # The view also guards this, but keep serializer robust.
            raise serializers.ValidationError({"detail": _("Not authenticated.")})

        old = attrs.get("old_password")
        if not user.check_password(old):
            raise serializers.ValidationError({"old_password": _("Your old password was entered incorrectly.")})

        p1 = attrs.get("new_password1")
        p2 = attrs.get("new_password2")
        if p1 != p2:
            raise serializers.ValidationError({"new_password2": _("Passwords do not match.")})

        # Django's validators (min length, common, numeric, etc.)
        validate_password(p1, user=user)
        return attrs


class PasswordChangeView(APIView):
    """
    Allow an authenticated user to change their password.
    - CSRF protected.
    - Throttled with scope `auth-password-change`.
    - Returns 204 on success.
    """
    permission_classes = [permissions.IsAuthenticated]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "auth-password-change"

    @extend_schema(
        operation_id="auth_password_change",
        summary="Change current user's password",
        request=_PasswordChangeSerializer,
        responses={
            204: OpenApiResponse(description="Password changed"),
            400: OpenApiResponse(description="Validation error"),
            401: OpenApiResponse(description="Not authenticated"),
            429: OpenApiResponse(description="Too many attempts (throttled)"),
        },
    )
    def post(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return Response({"detail": _("Not authenticated.")}, status=status.HTTP_401_UNAUTHORIZED)

        ser = _PasswordChangeSerializer(data=request.data, context={"request": request})
        ser.is_valid(raise_exception=True)

        # Persist new password and keep the session valid
        user = request.user
        new_password = ser.validated_data["new_password1"]
        user.set_password(new_password)
        user.save(update_fields=["password"])
        update_session_auth_hash(request, user)

        return Response(status=status.HTTP_204_NO_CONTENT)
