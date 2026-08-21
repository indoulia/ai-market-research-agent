"""close DB-level immutability gaps found in the 2026-08-21 QA/integration audit

Revision ID: 0090_immutability_hardening
Revises: 0089_merge_0088_heads

NOTE: `revision` is deliberately shorter than the filename/docstring title --
`alembic_version.version_num` is `VARCHAR(32)`, and the descriptive filename-length
string does not fit (hit this live: the first upgrade attempt against a real Postgres
instance failed on the final `UPDATE alembic_version` with `StringDataRightTruncation`).

Renumbered from the original 0087 (onto 0086_api_pref_profile) to 0090 (onto
0089_merge_0088_heads) after EPIC-M1.111/M1.112/M1.145 landed on main concurrently and
claimed 0087/0088 for themselves (resolved by main's own 0089_merge_heads_0088). No
schema change, filename/revision-id/down_revision only -- same pattern as 0086's own
two prior renumberings.

Two gaps, both defense-in-depth against bulk/raw-SQL writes that bypass the
ORM `before_update` guards (the exact reason 0006 added a DB trigger for
`predictions` in the first place -- SQLAlchemy's `Query.update()`/Core
`update()` never fire ORM events):

1. `predictions_enforce_immutability` (0006) only covers the 11 columns that
   existed at the time. `app.recommendations.IMMUTABLE_FIELDS` has since grown
   to include `consensus_contract_version` (0008), `horizon_selection_version`
   (0010), `scoring_contract_version` (0012) and `opportunity_score` -- none of
   which the trigger was ever updated to protect. `CREATE OR REPLACE` the same
   function/trigger with the full, current column list.
2. `prediction_outcomes` (app.outcomes) and `recommendation_revisions`
   (app.recommendation_revision) each define an ORM immutability guard but,
   unlike `predictions`, never got an equivalent DB trigger. Add one for each,
   mirroring 0006's pattern exactly.
"""
from alembic import op

revision = "0090_immutability_hardening"
down_revision = "0089_merge_0088_heads"
branch_labels = None
depends_on = None

_PREDICTIONS_FUNCTION = "predictions_enforce_immutability"
_PREDICTIONS_TRIGGER = "predictions_immutability_trigger"

# Mirrors app/recommendations.py IMMUTABLE_FIELDS. `status` stays excluded so
# outcome evaluation can still transition it OPEN -> EVALUATED.
_PREDICTIONS_IMMUTABLE_COLUMNS = (
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
    "consensus_contract_version",
    "horizon_selection_version",
    "scoring_contract_version",
    "opportunity_score",
)

_OUTCOMES_FUNCTION = "prediction_outcomes_enforce_immutability"
_OUTCOMES_TRIGGER = "prediction_outcomes_immutability_trigger"

# Mirrors app/outcomes.py IMMUTABLE_FIELDS -- every column on this table.
_OUTCOMES_IMMUTABLE_COLUMNS = (
    "prediction_id",
    "evaluation_date",
    "highest_price",
    "lowest_price",
    "closing_price",
    "maximum_return",
    "maximum_drawdown",
    "actual_return",
    "prediction_error",
    "target_hit",
    "stop_hit",
    "outcome",
    "label_methodology_version",
)

_REVISIONS_FUNCTION = "recommendation_revisions_enforce_immutability"
_REVISIONS_TRIGGER = "recommendation_revisions_immutability_trigger"

# Mirrors app/recommendation_revision.py IMMUTABLE_FIELDS -- every column on this table.
_REVISIONS_IMMUTABLE_COLUMNS = (
    "original_prediction_id",
    "previous_prediction_id",
    "revised_prediction_id",
    "version_number",
    "revision_reason",
    "triggering_evidence_revalidation_check_id",
    "revised_at",
    "revision_rule_version",
    "created_at",
)


def _create_trigger(table: str, function_name: str, trigger_name: str, columns: tuple[str, ...]) -> None:
    condition = " OR ".join(f"NEW.{col} IS DISTINCT FROM OLD.{col}" for col in columns)
    op.execute(
        f"""
        CREATE OR REPLACE FUNCTION {function_name}() RETURNS trigger AS $$
        BEGIN
            IF {condition} THEN
                RAISE EXCEPTION
                    '{table} % immutable fields cannot be modified after creation', OLD.id
                    USING ERRCODE = 'integrity_constraint_violation';
            END IF;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
        """
    )
    op.execute(f"DROP TRIGGER IF EXISTS {trigger_name} ON {table};")
    op.execute(
        f"""
        CREATE TRIGGER {trigger_name}
        BEFORE UPDATE ON {table}
        FOR EACH ROW
        EXECUTE FUNCTION {function_name}();
        """
    )


def _drop_trigger(function_name: str, trigger_name: str, table: str) -> None:
    op.execute(f"DROP TRIGGER IF EXISTS {trigger_name} ON {table};")
    op.execute(f"DROP FUNCTION IF EXISTS {function_name}();")


def upgrade() -> None:
    _create_trigger("predictions", _PREDICTIONS_FUNCTION, _PREDICTIONS_TRIGGER, _PREDICTIONS_IMMUTABLE_COLUMNS)
    _create_trigger("prediction_outcomes", _OUTCOMES_FUNCTION, _OUTCOMES_TRIGGER, _OUTCOMES_IMMUTABLE_COLUMNS)
    _create_trigger(
        "recommendation_revisions", _REVISIONS_FUNCTION, _REVISIONS_TRIGGER, _REVISIONS_IMMUTABLE_COLUMNS
    )


def downgrade() -> None:
    _drop_trigger(_REVISIONS_FUNCTION, _REVISIONS_TRIGGER, "recommendation_revisions")
    _drop_trigger(_OUTCOMES_FUNCTION, _OUTCOMES_TRIGGER, "prediction_outcomes")
    # Restore the original (0006) 11-column definition of the predictions trigger rather
    # than dropping it outright, so downgrading this migration alone doesn't also undo 0006.
    _create_trigger(
        "predictions",
        _PREDICTIONS_FUNCTION,
        _PREDICTIONS_TRIGGER,
        (
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
        ),
    )
