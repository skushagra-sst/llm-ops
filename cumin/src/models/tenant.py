from dataclasses import dataclass


@dataclass
class Tenant:
    id: str
    name: str
    is_active: bool = True

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Tenant):
            return NotImplemented
        return self.id == other.id

    def __hash__(self) -> int:
        return hash(self.id)
