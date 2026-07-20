from typing import Protocol


class PlannerActionsRepo(Protocol):
    def ensure_table(self) -> None: ...

    def list_actions(self, unique_id: str) -> list[dict]: ...

    def add_action(self, unique_id: str, action_type: str, note_text: str,
                    override_trust_level: str | None, planner_name: str) -> dict: ...
