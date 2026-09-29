import hashlib
import hmac
import secrets

from src.models.api_key import ApiKey
from src.models.tenant import Tenant


class AuthenticationError(Exception):
    pass


class TenantManager:
    def __init__(self) -> None:
        self._tenants: dict[str, Tenant] = {}
        self._keys: dict[str, ApiKey] = {}

    def get_tenant(self, tenant_id: str) -> Tenant:
        return self._tenants[tenant_id]

    def add_tenant(self, tenant: Tenant) -> None:
        self._tenants[tenant.id] = tenant

    def issue_api_key(self, tenant_id: str) -> str:
        if tenant_id not in self._tenants:
            raise KeyError(tenant_id)

        prefix = secrets.token_urlsafe(6)
        raw_key = f"{prefix}.{secrets.token_urlsafe(24)}"
        self._keys[prefix] = ApiKey(
            prefix=prefix,
            secret_hash=_hash_key(raw_key),
            tenant_id=tenant_id,
        )
        return raw_key

    def authenticate(self, raw_key: str) -> Tenant:
        prefix, separator, _secret = raw_key.partition(".")
        record = self._keys.get(prefix)
        if separator == "" or record is None:
            raise AuthenticationError("invalid api key")
        if not hmac.compare_digest(_hash_key(raw_key), record.secret_hash):
            raise AuthenticationError("invalid api key")

        tenant = self._tenants.get(record.tenant_id)
        if tenant is None or not tenant.is_active:
            raise AuthenticationError("invalid api key")
        return tenant


def _hash_key(raw_key: str) -> str:
    return hashlib.sha256(raw_key.encode()).hexdigest()
