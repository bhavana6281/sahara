from typing import Literal, Optional, Protocol

ReviewedFilter = Literal["all", "unreviewed"]
Decision = Literal["confirmed_issue", "looks_fine", "needs_field_check", "corrected"]


class ReadinessRepo(Protocol):
    def ensure_table(self) -> None: ...

    def summary(self) -> dict: ...

    def review_queue(self, reviewed: ReviewedFilter = "all", limit: int = 200) -> list[dict]: ...

    def list_decisions(self, unique_id: str) -> list[dict]: ...

    def add_decision(self, unique_id: str, reviewer: str, decision: str,
                      note: str, leverage_score: int) -> dict: ...
