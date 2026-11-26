"""Distinguish Keycloak reservation and terminal decisions in Bind ordering."""

from alembic import op

revision = "0019"
down_revision = "0018"
branch_labels = None
depends_on = None

_TABLE = "bind_sandbox_dispatch_order"
_CONSTRAINT = "ck_bind_sandbox_dispatch_resolution"
_SANDBOX = "resolution IN ('REVOKED_BEFORE_DISPATCH', 'DISPATCH_ALREADY_COMMITTED')"
_KEYCLOAK = """resolution IN (
    'KEYCLOAK_RESERVED', 'KEYCLOAK_REVOKED_BEFORE_DISPATCH', 'KEYCLOAK_DISPATCH_ALREADY_COMMITTED'
)"""


_OPERATOR_REVOCATION = """CREATE OR REPLACE FUNCTION public.revoke_sandbox_authorization(target_id text, operator_reason text)
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

    {scope_guard}

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

_SCOPE_GUARD = """IF NOT public.sandbox_revocation_scope_allows(target_id) THEN
                RAISE EXCEPTION 'Sandbox authorization binding required' USING ERRCODE = '42501';
            END IF;"""


def upgrade() -> None:
    op.drop_constraint(_CONSTRAINT, _TABLE, type_="check")
    op.create_check_constraint(_CONSTRAINT, _TABLE, f"{_SANDBOX} OR {_KEYCLOAK}")
    op.execute(
        """CREATE TABLE public.bind_sandbox_revocation_scopes (
            authorization_id text PRIMARY KEY
                CHECK (authorization_id ~ '^laba:v2:sha256:[0-9a-f]{64}$')
        )"""
    )
    op.execute("REVOKE ALL ON public.bind_sandbox_revocation_scopes FROM PUBLIC")
    op.execute(
        """CREATE FUNCTION public.sandbox_revocation_scope_allows(target_id text)
        RETURNS boolean LANGUAGE sql STABLE
        SET search_path = pg_catalog, pg_temp AS $$
            SELECT (
                EXISTS (
                    SELECT 1 FROM public.bind_sandbox_revocation_scopes WHERE authorization_id = target_id
                ) OR EXISTS (
                    SELECT 1 FROM public.bind_effect_states
                    WHERE authorization_id = target_id AND effect_provenance = 'SANDBOX_PRE_DISPATCH_V1'
                )
            ) AND NOT EXISTS (
                SELECT 1 FROM public.bind_keycloak_dispatch_intents AS intent
                JOIN public.bind_effect_states AS effect USING (operation_id)
                WHERE effect.authorization_id = target_id
            )
        $$"""
    )
    # Preserve the conservative ordering of an old cancellation on a Keycloak
    # reservation. Historical operator audit rows keep their original values.
    op.execute(
        """UPDATE public.bind_sandbox_dispatch_order AS ordering
        SET resolution = 'KEYCLOAK_REVOKED_BEFORE_DISPATCH'
        WHERE ordering.resolution = 'REVOKED_BEFORE_DISPATCH'
          AND EXISTS (
              SELECT 1 FROM public.bind_keycloak_dispatch_intents AS intent
              JOIN public.bind_effect_states AS effect USING (operation_id)
              WHERE effect.authorization_id = ordering.authorization_id
          )"""
    )
    op.execute(_OPERATOR_REVOCATION.replace("{scope_guard}", _SCOPE_GUARD))


def downgrade() -> None:
    op.execute("LOCK TABLE public.bind_sandbox_dispatch_order IN ACCESS EXCLUSIVE MODE")
    op.execute(
        """DO $$
        BEGIN
            IF EXISTS (
                SELECT 1 FROM public.bind_sandbox_dispatch_order
                WHERE resolution IN (
                    'KEYCLOAK_RESERVED', 'KEYCLOAK_REVOKED_BEFORE_DISPATCH', 'KEYCLOAK_DISPATCH_ALREADY_COMMITTED'
                )
            ) THEN
                RAISE EXCEPTION 'Cannot downgrade 0019 with Keycloak dispatch ordering history';
            END IF;
        END
        $$"""
    )
    op.drop_constraint(_CONSTRAINT, _TABLE, type_="check")
    op.create_check_constraint(_CONSTRAINT, _TABLE, _SANDBOX)
    op.execute(_OPERATOR_REVOCATION.replace("{scope_guard}", ""))
    op.execute("DROP FUNCTION public.sandbox_revocation_scope_allows(text)")
    op.drop_table("bind_sandbox_revocation_scopes", schema="public")
