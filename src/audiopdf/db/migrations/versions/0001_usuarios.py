"""usuários, sessões e dono dos livros

Revision ID: 0001
Revises:
"""
import sqlalchemy as sa
from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column("email", sa.String(254), nullable=False),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column("role", sa.String(10), nullable=False, server_default="user"),
        sa.Column("active", sa.Boolean, nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.Float, nullable=False),
        sa.Column("last_login", sa.Float, nullable=True),
    )
    op.create_index("ix_users_email", "users", ["email"], unique=True)
    op.create_table(
        "sessions",
        sa.Column("token_hash", sa.String(64), primary_key=True),
        sa.Column("user_id", sa.String(32), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("created_at", sa.Float, nullable=False),
        sa.Column("expires_at", sa.Float, nullable=False),
    )
    op.create_index("ix_sessions_user_id", "sessions", ["user_id"])
    op.create_table(
        "books",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column("owner_id", sa.String(32), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("created_at", sa.Float, nullable=False),
    )
    op.create_index("ix_books_owner_id", "books", ["owner_id"])


def downgrade() -> None:
    op.drop_table("books")
    op.drop_table("sessions")
    op.drop_table("users")
