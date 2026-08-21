"""Shared test isolation fixtures.

EPIC-M3.7: ``api.rate_limit.default_limiter`` is a module-level singleton
(by design -- EPIC-M1.132's real, enforced, in-memory fixed-window
limiter). Every test file that builds a ``TestClient(app)`` shares that
one instance across the *entire* pytest process, all keyed under the
same identity (``TestClient``'s default ``client.host`` of
``"testclient"``, no auth). With enough API-hitting tests running inside
one fixed 60s window, cumulative requests from unrelated, otherwise
passing test files push later ones over the limit and they start seeing
spurious 429s -- reproduced on `origin/autonomous/epic-m3-5` (this
branch's own base, before any EPIC-M3.7 change) via
``python -m pytest tests/test_api_tracking.py::test_predictions_list_pagination_covers_every_item_once``
run after the rest of the API-heavy suite. Resetting the limiter's
window before each test restores real per-test isolation without
changing the limiter's actual (correct) production behavior.
"""

from __future__ import annotations

import pytest

from api.rate_limit import default_limiter


@pytest.fixture(autouse=True)
def _reset_rate_limiter():
    default_limiter._hits.clear()
    yield
