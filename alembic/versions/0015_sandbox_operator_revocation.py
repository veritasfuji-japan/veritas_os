"""Permit scoped Sandbox revocation by authenticated PostgreSQL operators."""

from alembic import op

revision = "0015"
down_revision = "0014"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """CREATE TABLE public.bind_sandbox_revocation_grants (
            operator_role oid NOT NULL,
            operator_name name NOT NULL,
            authorization_id text NOT NULL
                CHECK (authorization_id ~ '^laba:v2:sha256:[0-9a-f]{64}$'),
            PRIMARY KEY (operator_role, authorization_id)
        )"""
    )
    op.execute(
        """CREATE TABLE public.bind_sandbox_revocation_audit (
            audit_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            operator_role oid NOT NULL,
            operator_name name NOT NULL,
            authorization_id text NOT NULL
                REFERENCES public.bind_sandbox_dispatch_order (authorization_id),
            reason text NOT NULL,
            resolution text NOT NULL CHECK (
                resolution IN ('REVOKED_BEFORE_DISPATCH', 'DISPATCH_ALREADY_COMMITTED')
            ),
            recorded_at timestamptz NOT NULL DEFAULT pg_catalog.clock_timestamp()
        )"""
    )
    op.execute("REVOKE ALL ON public.bind_sandbox_revocation_grants, public.bind_sandbox_revocation_audit FROM PUBLIC")
    op.execute(
        """CREATE FUNCTION public.revoke_sandbox_authorization(target_id text, operator_reason text)
        RETURNS TABLE (audit_id bigint, resolution text)
        LANGUAGE plpgsql
        SECURITY DEFINER
        SET search_path = pg_catalog, pg_temp
        AS $$
        DECLARE
            actor_oid oid;
            result text;
        BEGIN
            IF target_id IS NULL OR target_id !~ '^laba:v2:sha256:[0-9a-f]{64}$'
                OR operator_reason IS NULL
                OR operator_reason !~ '[^[:space:]]'
                OR char_length(operator_reason) > 512 THEN
                RAISE EXCEPTION 'Invalid sandbox revocation request' USING ERRCODE = '22023';
            END IF;

            SELECT rol.oid INTO actor_oid
                FROM pg_catalog.pg_roles AS rol WHERE rol.rolname = session_user;
            -- A logical restore can omit the ACL and restore default PUBLIC
            -- execution. Require an explicit grant to the login itself.
            IF NOT EXISTS (
                SELECT 1
                FROM pg_catalog.pg_proc AS routine
                CROSS JOIN LATERAL pg_catalog.aclexplode(routine.proacl) AS privilege
                WHERE routine.oid = 'public.revoke_sandbox_authorization(text,text)'::pg_catalog.regprocedure
                    AND privilege.grantee = actor_oid AND privilege.privilege_type = 'EXECUTE'
            ) THEN
                RAISE EXCEPTION 'Sandbox revocation execution grant required' USING ERRCODE = '42501';
            END IF;
            PERFORM 1 FROM public.bind_sandbox_revocation_grants AS scope
                WHERE scope.operator_role = actor_oid AND scope.operator_name = session_user
                    AND scope.authorization_id = target_id
                FOR KEY SHARE;
            IF NOT FOUND THEN
                RAISE EXCEPTION 'Sandbox revocation scope denied' USING ERRCODE = '42501';
            END IF;

            INSERT INTO public.bind_sandbox_dispatch_order AS ordering (authorization_id, resolution)
                VALUES (target_id, 'REVOKED_BEFORE_DISPATCH')
                ON CONFLICT (authorization_id) DO UPDATE SET resolution = ordering.resolution
                RETURNING ordering.resolution INTO result;

            RETURN QUERY
                INSERT INTO public.bind_sandbox_revocation_audit AS audit
                    (operator_role, operator_name, authorization_id, reason, resolution)
                    VALUES (actor_oid, session_user, target_id, operator_reason, result)
                    RETURNING audit.audit_id, audit.resolution;
        END
        $$"""
    )
    op.execute("REVOKE ALL ON FUNCTION public.revoke_sandbox_authorization(text, text) FROM PUBLIC")


def downgrade() -> None:
    op.execute("LOCK TABLE public.bind_sandbox_revocation_audit IN ACCESS EXCLUSIVE MODE")
    op.execute(
        """DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM public.bind_sandbox_revocation_audit) THEN
                RAISE EXCEPTION 'Cannot downgrade 0015 with recorded sandbox operator revocations';
            END IF;
        END
        $$"""
    )
    op.execute("DROP FUNCTION public.revoke_sandbox_authorization(text, text)")
    op.drop_table("bind_sandbox_revocation_audit", schema="public")
    op.drop_table("bind_sandbox_revocation_grants", schema="public")
