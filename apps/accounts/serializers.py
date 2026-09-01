from django.db import connection
from rest_framework import serializers
from rest_framework_simplejwt.exceptions import InvalidToken, TokenError
from rest_framework_simplejwt.serializers import (
    TokenObtainPairSerializer,
    TokenRefreshSerializer,
)
from rest_framework_simplejwt.tokens import RefreshToken

from apps.accounts.authentication import SCHEMA_CLAIM
from apps.accounts.models import User


class SchemaScopedTokenObtainPairSerializer(TokenObtainPairSerializer):
    @classmethod
    def get_token(cls, user):
        token = super().get_token(user)
        # SimpleJWT copies custom claims from the refresh token onto every
        # refreshed access token, so setting these once here is enough.
        token[SCHEMA_CLAIM] = connection.schema_name
        token["role"] = user.role
        return token


class SchemaScopedTokenRefreshSerializer(TokenRefreshSerializer):
    def validate(self, attrs):
        try:
            refresh = RefreshToken(attrs["refresh"])
        except TokenError as exc:
            raise InvalidToken(str(exc)) from exc
        if refresh.get(SCHEMA_CLAIM) != connection.schema_name:
            raise InvalidToken("refresh token was issued for a different tenant")
        return super().validate(attrs)


class MeSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ("id", "email", "first_name", "last_name", "role")
        read_only_fields = ("email", "role")
