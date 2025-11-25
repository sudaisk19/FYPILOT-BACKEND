"""update submission grading fields

Revision ID: update_submission_grading
Revises: move_due_at_total_marks
Create Date: 2026-02-11

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'update_submission_grading'
down_revision: Union[str, Sequence[str], None] = ('move_due_at_total_marks', '05bbb0352d41')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Check if old columns exist before dropping (idempotent migration)
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    columns = [col['name'] for col in inspector.get_columns('submissions')]
    
    # Remove old grading fields if they exist
    if 'obtained_marks' in columns:
        op.drop_column('submissions', 'obtained_marks')
    if 'graded_by' in columns:
        op.drop_column('submissions', 'graded_by')
    if 'graded_at' in columns:
        op.drop_column('submissions', 'graded_at')
    if 'feedback' in columns:
        op.drop_column('submissions', 'feedback')
    
    # Add new supervisor grading fields if they don't exist
    if 'supervisor_marks' not in columns:
        op.add_column('submissions', sa.Column('supervisor_marks', sa.Numeric(), nullable=True))
    if 'supervisor_feedback' not in columns:
        op.add_column('submissions', sa.Column('supervisor_feedback', sa.Text(), nullable=True))
    if 'supervisor_graded_at' not in columns:
        op.add_column('submissions', sa.Column('supervisor_graded_at', sa.DateTime(timezone=True), nullable=True))
    
    # Add new admin grading fields if they don't exist
    if 'admin_marks' not in columns:
        op.add_column('submissions', sa.Column('admin_marks', sa.Numeric(), nullable=True))
    if 'admin_feedback' not in columns:
        op.add_column('submissions', sa.Column('admin_feedback', sa.Text(), nullable=True))
    if 'admin_graded_at' not in columns:
        op.add_column('submissions', sa.Column('admin_graded_at', sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    # Remove new fields
    op.drop_column('submissions', 'admin_graded_at')
    op.drop_column('submissions', 'admin_feedback')
    op.drop_column('submissions', 'admin_marks')
    op.drop_column('submissions', 'supervisor_graded_at')
    op.drop_column('submissions', 'supervisor_feedback')
    op.drop_column('submissions', 'supervisor_marks')
    
    # Restore old grading fields
    op.add_column('submissions', sa.Column('feedback', sa.Text(), nullable=True))
    op.add_column('submissions', sa.Column('graded_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('submissions', sa.Column('graded_by', sa.dialects.postgresql.UUID(as_uuid=True), nullable=True))
    op.add_column('submissions', sa.Column('obtained_marks', sa.Numeric(), nullable=True))
    
    # Recreate foreign key for graded_by
    op.create_foreign_key('submissions_graded_by_fkey', 'submissions', 'users', ['graded_by'], ['user_id'])
