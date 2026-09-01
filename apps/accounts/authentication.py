from django.db import connection
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework_simplejwt.exceptions import InvalidToken

SCHEMA_CLAIM = "schema"


class TenantBoundJWTAuthentication(JWTAuthentication):
    """Reject a token whose `schema` claim != the schema this request resolved
    to. Auth is per-schema, so without this a token minted in tenant A's schema
    would authenticate against tenant B's user table by primary-key collision.
    """

    def get_validated_token(self, raw_token):
        token = super().get_validated_token(raw_token)
        if token.get(SCHEMA_CLAIM) != connection.schema_name:
            raise InvalidToken("token was issued for a different tenant")
        return token
