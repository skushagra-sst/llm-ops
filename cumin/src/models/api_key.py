from dataclasses import dataclass


@dataclass(frozen=True)
class ApiKey:
    prefix: str
    secret_hash: str
    tenant_id: str
