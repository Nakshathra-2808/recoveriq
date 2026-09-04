import os
import re

MIGRATION_PATH = os.path.join(
    os.path.dirname(__file__), "..", "..", "supabase", "migrations", "20260828000000_stage2b_tenant_rls_policies.sql"
)

EXPECTED_TABLES = [
    "merchants",
    "profiles",
    "customers",
    "batches",
    "payments",
    "payment_failures",
    "policies",
    "recovery_cases",
    "recovery_actions",
    "recovery_outcomes",
    "action_statistics",
    "baseline_results",
    "audit_logs",
]


def test_rls_migration_file_exists():
    """Verify that Stage 2B RLS migration file exists."""
    assert os.path.isfile(MIGRATION_PATH), f"Migration file not found at {MIGRATION_PATH}"


def test_rls_migration_security_definer_functions():
    """Verify that helper functions are defined with SECURITY DEFINER and STABLE."""
    with open(MIGRATION_PATH, "r", encoding="utf-8") as f:
        sql = f.read()

    assert "CREATE OR REPLACE FUNCTION public.get_auth_merchant_id()" in sql
    assert "CREATE OR REPLACE FUNCTION public.get_auth_user_role()" in sql
    assert "CREATE OR REPLACE FUNCTION public.is_merchant_member" in sql
    assert "CREATE OR REPLACE FUNCTION public.is_merchant_admin_or_owner" in sql
    assert "CREATE OR REPLACE FUNCTION public.is_merchant_operator_or_above" in sql

    # Security check: must use SECURITY DEFINER to prevent recursive RLS evaluations
    assert "SECURITY DEFINER SET search_path = public, pg_temp STABLE" in sql


def test_rls_migration_covers_all_13_tables():
    """Verify that RLS policies are applied across all 13 RecoverIQ tables."""
    with open(MIGRATION_PATH, "r", encoding="utf-8") as f:
        sql = f.read()

    for table in EXPECTED_TABLES:
        # Check for policy creation targeting each table
        pattern = rf'CREATE\s+POLICY\s+"[^"]+"\s+ON\s+{table}'
        matches = re.findall(pattern, sql, re.IGNORECASE)
        assert len(matches) > 0, f"Table '{table}' has no RLS policies defined in migration!"


def test_rls_migration_no_insecure_using_true():
    """Verify that no insecure 'USING (true)' or 'WITH CHECK (true)' policies exist."""
    with open(MIGRATION_PATH, "r", encoding="utf-8") as f:
        sql = f.read()

    # Search for insecure open policies
    insecure_using = re.findall(r'USING\s*\(\s*true\s*\)', sql, re.IGNORECASE)
    insecure_check = re.findall(r'WITH\s+CHECK\s*\(\s*true\s*\)', sql, re.IGNORECASE)

    assert len(insecure_using) == 0, f"Found insecure USING (true) policies: {insecure_using}"
    assert len(insecure_check) == 0, f"Found insecure WITH CHECK (true) policies: {insecure_check}"


def test_rls_migration_audit_logs_immutable():
    """Verify that audit_logs has NO UPDATE or DELETE policies."""
    with open(MIGRATION_PATH, "r", encoding="utf-8") as f:
        sql = f.read()

    update_policy = re.findall(r'CREATE\s+POLICY\s+"[^"]+"\s+ON\s+audit_logs\s+FOR\s+UPDATE', sql, re.IGNORECASE)
    delete_policy = re.findall(r'CREATE\s+POLICY\s+"[^"]+"\s+ON\s+audit_logs\s+FOR\s+DELETE', sql, re.IGNORECASE)

    assert len(update_policy) == 0, "audit_logs must NOT have UPDATE policy (immutable log invariant)"
    assert len(delete_policy) == 0, "audit_logs must NOT have DELETE policy (immutable log invariant)"
