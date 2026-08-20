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
        sa.Column("symbol", sa.String(32), nullable=False, unique=True),
        sa.Column("exchange", sa.String(16), nullable=False, server_default="NSE"),
        sa.Column("company_name", sa.String(256)),
        sa.Column("sector", sa.String(128)),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_table(
        "market_prices",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("stock_id", sa.Integer(), sa.ForeignKey("stocks.id"), nullable=False),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("open", sa.Numeric(18, 6), nullable=False),
        sa.Column("high", sa.Numeric(18, 6), nullable=False),
        sa.Column("low", sa.Numeric(18, 6), nullable=False),
        sa.Column("close", sa.Numeric(18, 6), nullable=False),
        sa.Column("volume", sa.BigInteger(), nullable=False),
        sa.Column("source", sa.String(64), nullable=False),
        sa.UniqueConstraint("stock_id", "timestamp", name="uq_market_prices_stock_timestamp"),
    )
    op.create_table(
        "predictions",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("stock_id", sa.Integer(), sa.ForeignKey("stocks.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("as_of_timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("entry_price", sa.Numeric(18, 6), nullable=False),
        sa.Column("horizon_days", sa.Integer(), nullable=False),
        sa.Column("target_return", sa.Numeric(10, 6), nullable=False),
        sa.Column("stop_return", sa.Numeric(10, 6), nullable=False),
        sa.Column("predicted_probability", sa.Numeric(10, 8), nullable=False),
        sa.Column("model_version", sa.String(64), nullable=False),
        sa.Column("feature_version", sa.String(64), nullable=False),
        sa.Column("status", sa.String(32), nullable=False, server_default="OPEN"),
    )
    op.create_table(
        "prediction_outcomes",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("prediction_id", sa.BigInteger(), sa.ForeignKey("predictions.id"), nullable=False, unique=True),
        sa.Column("evaluation_date", sa.DateTime(timezone=True), nullable=False),
        sa.Column("highest_price", sa.Numeric(18, 6), nullable=False),
        sa.Column("lowest_price", sa.Numeric(18, 6), nullable=False),
        sa.Column("closing_price", sa.Numeric(18, 6), nullable=False),
        sa.Column("maximum_return", sa.Numeric(10, 6), nullable=False),
        sa.Column("maximum_drawdown", sa.Numeric(10, 6), nullable=False),
        sa.Column("target_hit", sa.Boolean(), nullable=False),
        sa.Column("stop_hit", sa.Boolean(), nullable=False),
        sa.Column("outcome", sa.String(32), nullable=False),
    )
    op.create_table(
        "model_versions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("model_name", sa.String(128), nullable=False),
        sa.Column("version", sa.String(64), nullable=False, unique=True),
        sa.Column("feature_version", sa.String(64), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("metrics_json", sa.JSON()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

def downgrade():
    op.drop_table("model_versions")
    op.drop_table("prediction_outcomes")
    op.drop_table("predictions")
    op.drop_table("market_prices")
    op.drop_table("stocks")
