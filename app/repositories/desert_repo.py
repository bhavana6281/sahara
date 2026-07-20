from typing import Optional, Protocol


class DesertRepo(Protocol):
    def list_capabilities(self) -> list[str]: ...

    def desert_map(self, capability: str, state: Optional[str] = None) -> list[dict]: ...
