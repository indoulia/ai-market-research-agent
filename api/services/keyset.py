"""Generic keyset (cursor) pagination primitives, shared by every list
endpoint that ranks/orders a potentially large, growing table (M1.135's
recommendations feed, M1.139's discoveries/news/events).

Extracted from `api/services/recommendations.py` (EPIC-M1.135) once a
second endpoint needed the identical logic (EPIC-M1.139) -- see that
module's own comment for why the `id != cursor_id` guard in
`keyset_predicate` is load-bearing, not decoration.
"""

from __future__ import annotations

import base64
import binascii
import json
from datetime import datetime
from decimal import Decimal, InvalidOperation

from sqlalchemy import and_, or_

from ..errors import ValidationError


def encode_cursor(sort_value, row_id: int) -> str:
    if isinstance(sort_value, datetime):
        serialized = sort_value.isoformat()
    elif sort_value is None:
        serialized = None
    else:
        serialized = str(sort_value)
    raw = json.dumps({"v": serialized, "id": row_id}, separators=(",", ":")).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii")


def decode_cursor(cursor: str, *, is_datetime: bool) -> tuple[object, int]:
    try:
        raw = base64.urlsafe_b64decode(cursor.encode("ascii"))
        payload = json.loads(raw)
        value, row_id = payload["v"], int(payload["id"])
    except (ValueError, KeyError, TypeError, binascii.Error, json.JSONDecodeError) as exc:
        raise ValidationError("Invalid cursor.", field_errors={"cursor": "malformed"}) from exc

    if value is None:
        return None, row_id
    try:
        if is_datetime:
            return datetime.fromisoformat(value), row_id
        return Decimal(value), row_id
    except (ValueError, InvalidOperation) as exc:
        raise ValidationError("Invalid cursor.", field_errors={"cursor": "malformed"}) from exc


def keyset_predicate(sort_expr, id_col, cursor_value, cursor_id: int, *, descending: bool):
    # `id_col != cursor_id` is load-bearing: SQLite stores Numeric columns
    # as raw floats while SQLAlchemy quantizes the Python Decimal it hands
    # back to the column's declared scale, so a cursor value derived from
    # that quantized Decimal can differ from a row's true stored value by
    # <1e-6 -- enough for the previous page's own boundary row to
    # spuriously re-qualify on the next page without this guard.
    if descending:
        return and_(
            or_(sort_expr < cursor_value, and_(sort_expr == cursor_value, id_col < cursor_id)),
            id_col != cursor_id,
        )
    return and_(
        or_(sort_expr > cursor_value, and_(sort_expr == cursor_value, id_col > cursor_id)),
        id_col != cursor_id,
    )
