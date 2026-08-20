from alembic import op
import sqlalchemy as sa

revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "stocks",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("symbol", sa.String(32), nullable=False),
        sa.Column("exchange", sa.String(16), nullable=False),
        sa.Column("company_name", sa.String(256)),
        sa.Column("isin", sa.String(32), nullable=True),
        sa.Column("instrument_key", sa.String(128), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.UniqueConstraint("symbol"),
        sa.UniqueConstraint("isin"),
        sa.UniqueConstraint("instrument_key"),
    )
    op.create_index("ix_stocks_symbol", "stocks", ["symbol"])
    op.create_table(
        "market_prices",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("stock_id", sa.Integer(), sa.ForeignKey("stocks.id"), nullable=False),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("open", sa.Numeric(18, 6), nullable=False),
        sa.Column("high", sa.Numeric(18, 6), nullable=False),
        sa.Column("low", sa.Numeric(18, 6), nullable=False),
        sa.Column("close", sa.Numeric(18, 6), nullable=False),
        sa.Column("volume", sa.Integer(), nullable=False),
        sa.Column("source", sa.String(64), nullable=False),
    )
    op.create_index("ix_market_prices_stock_id", "market_prices", ["stock_id"])
    op.create_index("ix_market_prices_timestamp", "market_prices", ["timestamp"])
    op.create_table(
        "model_versions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("version", sa.String(64), nullable=False, unique=True),
        sa.Column("algorithm", sa.String(128), nullable=False),
        sa.Column("parameters_json", sa.Text()),
        sa.Column("training_start", sa.DateTime(timezone=True)),
        sa.Column("training_end", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "predictions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("stock_id", sa.Integer(), sa.ForeignKey("stocks.id"), nullable=False),
        sa.Column("as_of", sa.DateTime(timezone=True), nullable=False),
        sa.Column("horizon_days", sa.Integer(), nullable=False),
        sa.Column("predicted_return", sa.Numeric(18, 8), nullable=False),
        sa.Column("confidence", sa.Numeric(8, 6), nullable=False),
        sa.Column("model_version_id", sa.Integer(), sa.ForeignKey("model_versions.id")),
    )
    op.create_index("ix_predictions_stock_id", "predictions", ["stock_id"])
    op.create_index("ix_predictions_as_of", "predictions", ["as_of"])
    op.create_table(
        "prediction_outcomes",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("prediction_id", sa.Integer(), sa.ForeignKey("predictions.id"), nullable=False, unique=True),
        sa.Column("realized_return", sa.Numeric(18, 8), nullable=False),
        sa.Column("correct", sa.Boolean(), nullable=False),
        sa.Column("evaluated_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade():
    op.drop_table("prediction_outcomes")
    op.drop_table("predictions")
    op.drop_table("model_versions")
    op.drop_index("ix_market_prices_timestamp", table_name="market_prices")
    op.drop_index("ix_market_prices_stock_id", table_name="market_prices")
    op.drop_table("market_prices")
    op.drop_index("ix_stocks_symbol", table_name="stocks")
    op.drop_table("stocks")
