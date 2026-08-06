"""baseline schema (matches pre-Alembic Base.metadata.create_all state)

Revision ID: 0001
Revises:
Create Date: 2026-08-06

This migration documents the schema as it already exists in any database
created by the old create_all()-based startup. Running it against a fresh
database creates that same schema; running it against an existing database
that already has these tables is a no-op guarded by checkfirst.
"""
from alembic import op
import sqlalchemy as sa

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing = set(inspector.get_table_names())

    if "books" not in existing:
        op.create_table(
            "books",
            sa.Column("id", sa.Integer, primary_key=True, index=True),
            sa.Column("title", sa.String, index=True),
            sa.Column("file_path", sa.String),
            sa.Column("status", sa.String, server_default="queued"),
            sa.Column("progress", sa.Float, server_default="0.0"),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        )

    if "document_chunks" not in existing:
        op.create_table(
            "document_chunks",
            sa.Column("id", sa.Integer, primary_key=True, index=True),
            sa.Column("book_id", sa.Integer, sa.ForeignKey("books.id", ondelete="CASCADE")),
            sa.Column("page_number", sa.Integer),
            sa.Column("content", sa.Text),
            sa.Column("summary", sa.Text, nullable=True),
            sa.Column("characters", sa.Text, nullable=True),
            sa.Column("scenes", sa.Text, nullable=True),
            sa.Column("illustration_path", sa.String, nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        )

    if "characters" not in existing:
        op.create_table(
            "characters",
            sa.Column("id", sa.Integer, primary_key=True, index=True),
            sa.Column("book_id", sa.Integer, sa.ForeignKey("books.id", ondelete="CASCADE")),
            sa.Column("name", sa.String, index=True),
            sa.Column("aliases", sa.Text),
            sa.Column("visual_profile", sa.Text),
            sa.Column("mention_count", sa.Integer, server_default="1"),
        )

    if "page_characters" not in existing:
        op.create_table(
            "page_characters",
            sa.Column("character_id", sa.Integer, sa.ForeignKey("characters.id", ondelete="CASCADE")),
            sa.Column("chunk_id", sa.Integer, sa.ForeignKey("document_chunks.id", ondelete="CASCADE")),
        )

    if "jobs" not in existing:
        op.create_table(
            "jobs",
            sa.Column("id", sa.Integer, primary_key=True, index=True),
            sa.Column("book_id", sa.Integer, sa.ForeignKey("books.id", ondelete="CASCADE")),
            sa.Column("job_type", sa.String),
            sa.Column("status", sa.String, server_default="queued"),
            sa.Column("progress", sa.Float, server_default="0.0"),
            sa.Column("status_note", sa.Text),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        )

    if "page_assets" not in existing:
        op.create_table(
            "page_assets",
            sa.Column("id", sa.Integer, primary_key=True, index=True),
            sa.Column("chunk_id", sa.Integer, sa.ForeignKey("document_chunks.id", ondelete="CASCADE"), unique=True),
            sa.Column("visual_summary", sa.Text),
            sa.Column("key_objects", sa.Text),
            sa.Column("image_prompt", sa.Text),
            sa.Column("image_path", sa.String),
            sa.Column("seed", sa.Integer),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        )

    if "app_settings" not in existing:
        op.create_table(
            "app_settings",
            sa.Column("key", sa.String, primary_key=True),
            sa.Column("value", sa.String),
        )


def downgrade():
    op.drop_table("app_settings")
    op.drop_table("page_assets")
    op.drop_table("jobs")
    op.drop_table("page_characters")
    op.drop_table("characters")
    op.drop_table("document_chunks")
    op.drop_table("books")
