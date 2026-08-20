"""enforce recommendation immutability at the database boundary

Revision ID: 0006_predictions_trigger
Revises: 0005_prediction_confidence

NOTE: this branch (autonomous/epic-m1-4-sub-01) forks from `main` immediately after
EPIC-M1.4 merged, before EPIC-M1.5 (PR #14, unmerged at the time of writing) exists in
`main`. PR #14 also defines a migration numbered 0006 (`0006_outcome_actual_return`,
chaining from this same 0005 head). Whichever of these two PRs merges second will hit a
migration-history conflict (two revisions both claiming down_revision=0005) and must
renumber to 0007 with an updated down_revision before merging, then re-validate. This is
flagged in the Completion Report; not resolved here since it depends on merge order,
which is outside Claude's control now that Claude does not merge PRs.
"""
from alembic import op

revision = "0006_predictions_trigger"
down_revision = "0005_prediction_confidence"
branch_labels = None
depends_on = None

# Mirrors app/recommendations.py IMMUTABLE_FIELDS: the original recommendation fields
# that must never change after creation. `status` is intentionally excluded so M1.5's
# outcome evaluation can transition it OPEN -> EVALUATED.
_FUNCTION_NAME = "predictions_enforce_immutability"
_TRIGGER_NAME = "predictions_immutability_trigger"

_IMMUTABLE_COLUMNS = (
    "stock_id",
    "created_at",
    "as_of_timestamp",
    "entry_price",
    "horizon_days",
    "target_return",
    "stop_return",
    "predicted_probability",
    "confidence",
    "model_version",
    "feature_version",
)


def upgrade() -> None:
    condition = " OR ".join(f"NEW.{col} IS DISTINCT FROM OLD.{col}" for col in _IMMUTABLE_COLUMNS)
    op.execute(
        f"""
        CREATE OR REPLACE FUNCTION {_FUNCTION_NAME}() RETURNS trigger AS $$
        BEGIN
            IF {condition} THEN
                RAISE EXCEPTION
                    'recommendation % immutable fields cannot be modified after creation', OLD.id
                    USING ERRCODE = 'integrity_constraint_violation';
            END IF;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
        """
    )
    op.execute(
        f"""
        CREATE TRIGGER {_TRIGGER_NAME}
        BEFORE UPDATE ON predictions
        FOR EACH ROW
        EXECUTE FUNCTION {_FUNCTION_NAME}();
        """
    )


def downgrade() -> None:
    op.execute(f"DROP TRIGGER IF EXISTS {_TRIGGER_NAME} ON predictions;")
    op.execute(f"DROP FUNCTION IF EXISTS {_FUNCTION_NAME}();")
