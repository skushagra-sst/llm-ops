import hashlib
import hmac
import secrets

from src.models.api_key import ApiKey
from src.models.tenant import Tenant
from src.services.db import Database, utc_now


class AuthenticationError(Exception):
    pass


class TenantExists(Exception):
    pass


class TenantManager:
    def __init__(self, database: Database | None = None) -> None:
        self._db = database or Database()

    def list_tenants(self) -> list[Tenant]:
        rows = self._db.read("SELECT * FROM tenants ORDER BY name COLLATE NOCASE")
        return [_tenant(row) for row in rows]

    def get_tenant(self, tenant_id: str) -> Tenant:
        rows = self._db.read("SELECT * FROM tenants WHERE id = ?", (tenant_id,))
        if not rows:
            raise KeyError(tenant_id)
        return _tenant(rows[0])

    def add_tenant(self, tenant: Tenant) -> None:
        self._db.write(
            """
            INSERT INTO tenants (id, name, is_active, plan_id)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                name = excluded.name,
                is_active = excluded.is_active,
                plan_id = excluded.plan_id
            """,
            (tenant.id, tenant.name, int(tenant.is_active), tenant.plan_id),
        )

    def list_keys(self, tenant_id: str) -> list[str]:
        self.get_tenant(tenant_id)
        rows = self._db.read(
            "SELECT prefix FROM api_keys WHERE tenant_id = ? ORDER BY prefix",
            (tenant_id,),
        )
        return [row["prefix"] for row in rows]

    def key_rows(self, tenant_id: str) -> list[dict]:
        self.get_tenant(tenant_id)
        rows = self._db.read(
            "SELECT prefix, created_at FROM api_keys WHERE tenant_id = ? ORDER BY created_at DESC, prefix",
            (tenant_id,),
        )
        return [dict(row) for row in rows]

    def revoke_key(self, prefix: str) -> str:
        rows = self._db.read("SELECT tenant_id FROM api_keys WHERE prefix = ?", (prefix,))
        if not rows:
            raise KeyError(prefix)
        self._db.write("DELETE FROM api_keys WHERE prefix = ?", (prefix,))
        return rows[0]["tenant_id"]

    def set_active(self, tenant_id: str, is_active: bool) -> Tenant:
        self.get_tenant(tenant_id)
        self._db.write("UPDATE tenants SET is_active = ? WHERE id = ?", (int(is_active), tenant_id))
        return self.get_tenant(tenant_id)

    def create_tenant(self, tenant: Tenant) -> Tenant:
        rows = self._db.read("SELECT id FROM tenants WHERE id = ?", (tenant.id,))
        if rows:
            raise TenantExists(tenant.id)
        self._db.write(
            "INSERT INTO tenants (id, name, is_active, plan_id) VALUES (?, ?, ?, ?)",
            (tenant.id, tenant.name, int(tenant.is_active), tenant.plan_id),
        )
        return self.get_tenant(tenant.id)

    def rename(self, tenant_id: str, name: str) -> Tenant:
        self.get_tenant(tenant_id)
        self._db.write("UPDATE tenants SET name = ? WHERE id = ?", (name, tenant_id))
        return self.get_tenant(tenant_id)

    def delete_tenant(self, tenant_id: str) -> None:
        self.get_tenant(tenant_id)
        with self._db.transaction() as conn:
            conn.execute("DELETE FROM api_keys WHERE tenant_id = ?", (tenant_id,))
            conn.execute("DELETE FROM ledger WHERE tenant_id = ?", (tenant_id,))
            conn.execute("DELETE FROM idempotency WHERE tenant_id = ?", (tenant_id,))
            conn.execute("DELETE FROM audit WHERE tenant_id = ?", (tenant_id,))
            conn.execute("DELETE FROM tenants WHERE id = ?", (tenant_id,))

    def set_plan(self, tenant_id: str, plan_id: str) -> Tenant:
        self.get_tenant(tenant_id)
        self._db.write("UPDATE tenants SET plan_id = ? WHERE id = ?", (plan_id, tenant_id))
        return self.get_tenant(tenant_id)

    def issue_api_key(self, tenant_id: str) -> str:
        self.get_tenant(tenant_id)
        prefix = secrets.token_urlsafe(6)
        raw_key = f"{prefix}.{secrets.token_urlsafe(24)}"
        self._db.write(
            "INSERT INTO api_keys (prefix, secret_hash, tenant_id, created_at) VALUES (?, ?, ?, ?)",
            (prefix, _hash_key(raw_key), tenant_id, utc_now()),
        )
        return raw_key

    def authenticate(self, raw_key: str) -> Tenant:
        prefix, separator, _secret = raw_key.partition(".")
        if separator == "":
            raise AuthenticationError("invalid api key")
        rows = self._db.read("SELECT * FROM api_keys WHERE prefix = ?", (prefix,))
        if not rows:
            raise AuthenticationError("invalid api key")
        record = ApiKey(
            prefix=rows[0]["prefix"],
            secret_hash=rows[0]["secret_hash"],
            tenant_id=rows[0]["tenant_id"],
        )
        if not hmac.compare_digest(_hash_key(raw_key), record.secret_hash):
            raise AuthenticationError("invalid api key")
        tenant_rows = self._db.read("SELECT * FROM tenants WHERE id = ?", (record.tenant_id,))
        if not tenant_rows or not tenant_rows[0]["is_active"]:
            raise AuthenticationError("invalid api key")
        return _tenant(tenant_rows[0])


def _tenant(row) -> Tenant:
    return Tenant(
        id=row["id"],
        name=row["name"],
        is_active=bool(row["is_active"]),
        plan_id=row["plan_id"],
    )


def _hash_key(raw_key: str) -> str:
    return hashlib.sha256(raw_key.encode()).hexdigest()
