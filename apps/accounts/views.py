from rest_framework import generics
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView

from apps.accounts.serializers import (
    MeSerializer,
    SchemaScopedTokenObtainPairSerializer,
    SchemaScopedTokenRefreshSerializer,
)
from apps.core.audit import record


class LoginView(TokenObtainPairView):
    serializer_class = SchemaScopedTokenObtainPairSerializer
    throttle_scope = "login"

    def post(self, request, *args, **kwargs):
        actor = request.data.get("email", "unknown")
        try:
            response = super().post(request, *args, **kwargs)
        except Exception:
            record("auth.login_failed", actor=actor)
            raise
        record("auth.login", actor=actor)
        return response


class RefreshView(TokenRefreshView):
    serializer_class = SchemaScopedTokenRefreshSerializer


class LogoutView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        try:
            RefreshToken(request.data["refresh"]).blacklist()
        except (KeyError, TokenError):
            pass  # already invalid / not supplied — logout is idempotent
        record("auth.logout", actor=getattr(request.user, "email", "unknown"))
        return Response(status=205)


class MeView(generics.RetrieveUpdateAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = MeSerializer

    def get_object(self):
        return self.request.user
