"""Identity and institution foundations.

Revision ID: 0001_identity
Revises:
"""
import sqlalchemy as sa
from alembic import op

revision = "0001_identity"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("institutions", sa.Column("id", sa.Uuid(), primary_key=True), sa.Column("name", sa.String(160), nullable=False))
    op.create_table(
        "profiles",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("email", sa.String(320), nullable=False),
        sa.Column("role", sa.String(32), nullable=False, server_default="student"),
        sa.Column("institution_id", sa.Uuid(), sa.ForeignKey("institutions.id"), nullable=True),
        sa.CheckConstraint("role IN ('superadmin','admin','coordinator','teacher','student','analyst','ml_engineer','auditor')", name="valid_profile_role"),
    )
    op.execute("ALTER TABLE public.profiles ADD CONSTRAINT profiles_id_fkey FOREIGN KEY (id) REFERENCES auth.users(id) ON DELETE CASCADE")
    op.create_index("ix_profiles_institution_id", "profiles", ["institution_id"])
    op.execute("ALTER TABLE public.profiles ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE public.institutions ENABLE ROW LEVEL SECURITY")
    # No browser policies: identity and roles are read through the authorized API only.
    op.execute("""
    CREATE FUNCTION public.edumaster_new_user() RETURNS trigger
    LANGUAGE plpgsql SECURITY DEFINER SET search_path = '' AS $$
    BEGIN
      INSERT INTO public.profiles (id, email, role)
      VALUES (NEW.id, COALESCE(NEW.email, ''), 'student')
      ON CONFLICT (id) DO NOTHING;
      RETURN NEW;
    END;
    $$
    """)
    op.execute("CREATE TRIGGER edumaster_user_created AFTER INSERT ON auth.users FOR EACH ROW EXECUTE FUNCTION public.edumaster_new_user()")
    op.execute("INSERT INTO public.profiles (id, email, role) SELECT id, COALESCE(email, ''), 'student' FROM auth.users ON CONFLICT (id) DO NOTHING")


def downgrade():
    op.execute("DROP TRIGGER IF EXISTS edumaster_user_created ON auth.users")
    op.execute("DROP FUNCTION IF EXISTS public.edumaster_new_user()")
    op.drop_index("ix_profiles_institution_id", table_name="profiles")
    op.drop_table("profiles")
    op.drop_table("institutions")
