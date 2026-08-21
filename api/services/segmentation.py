"""SQL-expression equivalents of `app.discovery_segmentation`'s classifiers,
for server-side filtering/display in list endpoints (M1.135, M1.139).

Reuses that module's real, versioned, canonical thresholds/vocabulary --
never invents a second, incompatible one (see EPIC-M1.135's Completion
Report for the bug this replaced: an earlier version of the
`marketCapBucket` filter used its own wrong absolute-currency thresholds).
"""

from __future__ import annotations

from sqlalchemy import case

from app.discovery_segmentation import BUCKET_UNCLASSIFIED, LIQUIDITY_BUCKET_THRESHOLDS, MARKET_CAP_BUCKET_THRESHOLDS


def market_cap_bucket_expr(market_cap_col):
    return case(*[(market_cap_col >= threshold, bucket) for threshold, bucket in MARKET_CAP_BUCKET_THRESHOLDS], else_=BUCKET_UNCLASSIFIED)


def liquidity_bucket_expr(volume_ratio_col):
    return case(*[(volume_ratio_col >= threshold, bucket) for threshold, bucket in LIQUIDITY_BUCKET_THRESHOLDS], else_=BUCKET_UNCLASSIFIED)
