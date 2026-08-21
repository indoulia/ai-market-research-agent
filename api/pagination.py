"""Pagination, sorting and filtering conventions shared by list endpoints (EPIC-M1.132).

Convention (documented in docs/api/VERSIONING.md):
  - Page-based pagination via ``page`` (1-indexed) and ``pageSize`` query params.
  - ``sort`` query param: comma-separated field names, ``-`` prefix for descending
    (e.g. ``sort=-createdAt,symbol``).
  - Domain-specific filters are individual query params (e.g. ``status=OPEN``),
    documented per-endpoint; unknown filter params are rejected with
    ``MRA_VALIDATION_FAILED`` rather than silently ignored.
"""

from __future__ import annotations

from fastapi import Query

from .errors import ValidationError

DEFAULT_PAGE_SIZE = 20
MAX_PAGE_SIZE = 100


class PageParams:
    def __init__(
        self,
        page: int = Query(1, ge=1, description="1-indexed page number"),
        pageSize: int = Query(DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE, description="Items per page"),
    ) -> None:
        self.page = page
        self.page_size = pageSize

    @property
    def offset(self) -> int:
        return (self.page - 1) * self.page_size


def parse_sort(sort: str | None, allowed_fields: set[str]) -> list[tuple[str, bool]]:
    """Parse a ``sort`` query param into ``[(field, descending), ...]``.

    Raises ``ValidationError`` (-> MRA_VALIDATION_FAILED) on any field not in
    ``allowed_fields`` so clients get an explicit contract error instead of a
    silently-ignored sort key.
    """
    if not sort:
        return []
    clauses: list[tuple[str, bool]] = []
    for raw in sort.split(","):
        raw = raw.strip()
        if not raw:
            continue
        descending = raw.startswith("-")
        field = raw[1:] if descending else raw
        if field not in allowed_fields:
            raise ValidationError(
                f"Unknown sort field '{field}'.",
                field_errors={"sort": f"must be one of {sorted(allowed_fields)}"},
            )
        clauses.append((field, descending))
    return clauses
