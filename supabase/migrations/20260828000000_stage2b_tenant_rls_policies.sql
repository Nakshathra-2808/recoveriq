-- ============================================================================
-- RecoverIQ Database Schema Migration - Stage 2B
-- Migration: 20260828000000_stage2b_tenant_rls_policies.sql
-- Description: Production-ready Row Level Security (RLS) tenant isolation policies
--              and role-based permissions (owner, admin, operator, viewer).
-- ============================================================================

-- ============================================================================
-- 1. HELPER FUNCTIONS FOR AUTH & TENANT RESOLUTION
-- SECURITY DEFINER ensures these functions run with creator privileges to lookup
-- the authenticated user's profile and merchant without causing RLS recursion.
-- ============================================================================

CREATE OR REPLACE FUNCTION public.get_auth_merchant_id()
RETURNS UUID AS $$
DECLARE
    v_merchant_id UUID;
BEGIN
    SELECT merchant_id INTO v_merchant_id
    FROM public.profiles
    WHERE id = auth.uid() AND is_active = true
    LIMIT 1;

    RETURN v_merchant_id;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp STABLE;

CREATE OR REPLACE FUNCTION public.get_auth_user_role()
RETURNS VARCHAR(50) AS $$
DECLARE
    v_role VARCHAR(50);
BEGIN
    SELECT role INTO v_role
    FROM public.profiles
    WHERE id = auth.uid() AND is_active = true
    LIMIT 1;

    RETURN v_role;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp STABLE;

CREATE OR REPLACE FUNCTION public.is_merchant_member(target_merchant_id UUID)
RETURNS BOOLEAN AS $$
BEGIN
    RETURN target_merchant_id IS NOT NULL AND target_merchant_id = public.get_auth_merchant_id();
END;
$$ LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp STABLE;

CREATE OR REPLACE FUNCTION public.is_merchant_admin_or_owner(target_merchant_id UUID)
RETURNS BOOLEAN AS $$
BEGIN
    RETURN target_merchant_id IS NOT NULL 
       AND target_merchant_id = public.get_auth_merchant_id()
       AND public.get_auth_user_role() IN ('owner', 'admin');
END;
$$ LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp STABLE;

CREATE OR REPLACE FUNCTION public.is_merchant_operator_or_above(target_merchant_id UUID)
RETURNS BOOLEAN AS $$
BEGIN
    RETURN target_merchant_id IS NOT NULL 
       AND target_merchant_id = public.get_auth_merchant_id()
       AND public.get_auth_user_role() IN ('owner', 'admin', 'operator');
END;
$$ LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp STABLE;

-- Grant execution to authenticated users
GRANT EXECUTE ON FUNCTION public.get_auth_merchant_id() TO authenticated;
GRANT EXECUTE ON FUNCTION public.get_auth_user_role() TO authenticated;
GRANT EXECUTE ON FUNCTION public.is_merchant_member(UUID) TO authenticated;
GRANT EXECUTE ON FUNCTION public.is_merchant_admin_or_owner(UUID) TO authenticated;
GRANT EXECUTE ON FUNCTION public.is_merchant_operator_or_above(UUID) TO authenticated;

-- ============================================================================
-- 2. MERCHANTS TABLE POLICIES
-- - SELECT: Users can only view their own merchant organization.
-- - UPDATE: Only 'owner' and 'admin' roles can update merchant settings.
-- - INSERT/DELETE: Restricted (managed via service role or onboarding system).
-- ============================================================================

DROP POLICY IF EXISTS "merchants_select_tenant" ON merchants;
CREATE POLICY "merchants_select_tenant"
    ON merchants FOR SELECT
    TO authenticated
    USING (id = public.get_auth_merchant_id());

DROP POLICY IF EXISTS "merchants_update_admin" ON merchants;
CREATE POLICY "merchants_update_admin"
    ON merchants FOR UPDATE
    TO authenticated
    USING (public.is_merchant_admin_or_owner(id))
    WITH CHECK (public.is_merchant_admin_or_owner(id));

-- ============================================================================
-- 3. PROFILES TABLE POLICIES
-- - SELECT: Users can view their own profile and colleague profiles within their merchant.
-- - UPDATE: Users can update their own profile; admins/owners can update members of their merchant.
-- - INSERT: Users can register/create their profile matching auth.uid() and valid merchant.
-- ============================================================================

DROP POLICY IF EXISTS "profiles_select_tenant" ON profiles;
CREATE POLICY "profiles_select_tenant"
    ON profiles FOR SELECT
    TO authenticated
    USING (
        id = auth.uid() 
        OR merchant_id = public.get_auth_merchant_id()
    );

DROP POLICY IF EXISTS "profiles_update_self_or_admin" ON profiles;
CREATE POLICY "profiles_update_self_or_admin"
    ON profiles FOR UPDATE
    TO authenticated
    USING (
        id = auth.uid() 
        OR public.is_merchant_admin_or_owner(merchant_id)
    )
    WITH CHECK (
        (id = auth.uid() AND merchant_id = public.get_auth_merchant_id())
        OR public.is_merchant_admin_or_owner(merchant_id)
    );

DROP POLICY IF EXISTS "profiles_insert_self" ON profiles;
CREATE POLICY "profiles_insert_self"
    ON profiles FOR INSERT
    TO authenticated
    WITH CHECK (
        id = auth.uid()
        AND (
            public.get_auth_merchant_id() IS NULL
            OR merchant_id = public.get_auth_merchant_id()
        )
    );

-- ============================================================================
-- 4. CUSTOMERS TABLE POLICIES
-- - SELECT: All tenant members (including viewers).
-- - INSERT/UPDATE: Operators, admins, and owners.
-- - DELETE: Admins and owners.
-- ============================================================================

DROP POLICY IF EXISTS "customers_select_tenant" ON customers;
CREATE POLICY "customers_select_tenant"
    ON customers FOR SELECT
    TO authenticated
    USING (public.is_merchant_member(merchant_id));

DROP POLICY IF EXISTS "customers_insert_operator" ON customers;
CREATE POLICY "customers_insert_operator"
    ON customers FOR INSERT
    TO authenticated
    WITH CHECK (public.is_merchant_operator_or_above(merchant_id));

DROP POLICY IF EXISTS "customers_update_operator" ON customers;
CREATE POLICY "customers_update_operator"
    ON customers FOR UPDATE
    TO authenticated
    USING (public.is_merchant_operator_or_above(merchant_id))
    WITH CHECK (public.is_merchant_operator_or_above(merchant_id));

DROP POLICY IF EXISTS "customers_delete_admin" ON customers;
CREATE POLICY "customers_delete_admin"
    ON customers FOR DELETE
    TO authenticated
    USING (public.is_merchant_admin_or_owner(merchant_id));

-- ============================================================================
-- 5. BATCHES TABLE POLICIES
-- - SELECT: All tenant members.
-- - INSERT/UPDATE: Operators, admins, and owners.
-- - DELETE: Admins and owners.
-- ============================================================================

DROP POLICY IF EXISTS "batches_select_tenant" ON batches;
CREATE POLICY "batches_select_tenant"
    ON batches FOR SELECT
    TO authenticated
    USING (public.is_merchant_member(merchant_id));

DROP POLICY IF EXISTS "batches_insert_operator" ON batches;
CREATE POLICY "batches_insert_operator"
    ON batches FOR INSERT
    TO authenticated
    WITH CHECK (public.is_merchant_operator_or_above(merchant_id));

DROP POLICY IF EXISTS "batches_update_operator" ON batches;
CREATE POLICY "batches_update_operator"
    ON batches FOR UPDATE
    TO authenticated
    USING (public.is_merchant_operator_or_above(merchant_id))
    WITH CHECK (public.is_merchant_operator_or_above(merchant_id));

DROP POLICY IF EXISTS "batches_delete_admin" ON batches;
CREATE POLICY "batches_delete_admin"
    ON batches FOR DELETE
    TO authenticated
    USING (public.is_merchant_admin_or_owner(merchant_id));

-- ============================================================================
-- 6. PAYMENTS TABLE POLICIES
-- - SELECT: All tenant members.
-- - INSERT/UPDATE: Operators, admins, and owners.
-- ============================================================================

DROP POLICY IF EXISTS "payments_select_tenant" ON payments;
CREATE POLICY "payments_select_tenant"
    ON payments FOR SELECT
    TO authenticated
    USING (public.is_merchant_member(merchant_id));

DROP POLICY IF EXISTS "payments_insert_operator" ON payments;
CREATE POLICY "payments_insert_operator"
    ON payments FOR INSERT
    TO authenticated
    WITH CHECK (public.is_merchant_operator_or_above(merchant_id));

DROP POLICY IF EXISTS "payments_update_operator" ON payments;
CREATE POLICY "payments_update_operator"
    ON payments FOR UPDATE
    TO authenticated
    USING (public.is_merchant_operator_or_above(merchant_id))
    WITH CHECK (public.is_merchant_operator_or_above(merchant_id));

-- ============================================================================
-- 7. PAYMENT_FAILURES TABLE POLICIES
-- - SELECT: All tenant members.
-- - INSERT/UPDATE: Operators, admins, and owners.
-- ============================================================================

DROP POLICY IF EXISTS "payment_failures_select_tenant" ON payment_failures;
CREATE POLICY "payment_failures_select_tenant"
    ON payment_failures FOR SELECT
    TO authenticated
    USING (public.is_merchant_member(merchant_id));

DROP POLICY IF EXISTS "payment_failures_insert_operator" ON payment_failures;
CREATE POLICY "payment_failures_insert_operator"
    ON payment_failures FOR INSERT
    TO authenticated
    WITH CHECK (public.is_merchant_operator_or_above(merchant_id));

DROP POLICY IF EXISTS "payment_failures_update_operator" ON payment_failures;
CREATE POLICY "payment_failures_update_operator"
    ON payment_failures FOR UPDATE
    TO authenticated
    USING (public.is_merchant_operator_or_above(merchant_id))
    WITH CHECK (public.is_merchant_operator_or_above(merchant_id));

-- ============================================================================
-- 8. POLICIES (RECOVERY GUARDRAIL POLICIES) TABLE POLICIES
-- - SELECT: All tenant members.
-- - INSERT/UPDATE/DELETE: Only Admins and Owners (governance configuration).
-- ============================================================================

DROP POLICY IF EXISTS "policies_select_tenant" ON policies;
CREATE POLICY "policies_select_tenant"
    ON policies FOR SELECT
    TO authenticated
    USING (public.is_merchant_member(merchant_id));

DROP POLICY IF EXISTS "policies_insert_admin" ON policies;
CREATE POLICY "policies_insert_admin"
    ON policies FOR INSERT
    TO authenticated
    WITH CHECK (public.is_merchant_admin_or_owner(merchant_id));

DROP POLICY IF EXISTS "policies_update_admin" ON policies;
CREATE POLICY "policies_update_admin"
    ON policies FOR UPDATE
    TO authenticated
    USING (public.is_merchant_admin_or_owner(merchant_id))
    WITH CHECK (public.is_merchant_admin_or_owner(merchant_id));

DROP POLICY IF EXISTS "policies_delete_admin" ON policies;
CREATE POLICY "policies_delete_admin"
    ON policies FOR DELETE
    TO authenticated
    USING (public.is_merchant_admin_or_owner(merchant_id));

-- ============================================================================
-- 9. RECOVERY_CASES TABLE POLICIES
-- - SELECT: All tenant members.
-- - INSERT/UPDATE: Operators, admins, and owners.
-- ============================================================================

DROP POLICY IF EXISTS "recovery_cases_select_tenant" ON recovery_cases;
CREATE POLICY "recovery_cases_select_tenant"
    ON recovery_cases FOR SELECT
    TO authenticated
    USING (public.is_merchant_member(merchant_id));

DROP POLICY IF EXISTS "recovery_cases_insert_operator" ON recovery_cases;
CREATE POLICY "recovery_cases_insert_operator"
    ON recovery_cases FOR INSERT
    TO authenticated
    WITH CHECK (public.is_merchant_operator_or_above(merchant_id));

DROP POLICY IF EXISTS "recovery_cases_update_operator" ON recovery_cases;
CREATE POLICY "recovery_cases_update_operator"
    ON recovery_cases FOR UPDATE
    TO authenticated
    USING (public.is_merchant_operator_or_above(merchant_id))
    WITH CHECK (public.is_merchant_operator_or_above(merchant_id));

-- ============================================================================
-- 10. RECOVERY_ACTIONS TABLE POLICIES
-- - SELECT: All tenant members.
-- - INSERT/UPDATE: Operators, admins, and owners.
-- ============================================================================

DROP POLICY IF EXISTS "recovery_actions_select_tenant" ON recovery_actions;
CREATE POLICY "recovery_actions_select_tenant"
    ON recovery_actions FOR SELECT
    TO authenticated
    USING (public.is_merchant_member(merchant_id));

DROP POLICY IF EXISTS "recovery_actions_insert_operator" ON recovery_actions;
CREATE POLICY "recovery_actions_insert_operator"
    ON recovery_actions FOR INSERT
    TO authenticated
    WITH CHECK (public.is_merchant_operator_or_above(merchant_id));

DROP POLICY IF EXISTS "recovery_actions_update_operator" ON recovery_actions;
CREATE POLICY "recovery_actions_update_operator"
    ON recovery_actions FOR UPDATE
    TO authenticated
    USING (public.is_merchant_operator_or_above(merchant_id))
    WITH CHECK (public.is_merchant_operator_or_above(merchant_id));

-- ============================================================================
-- 11. RECOVERY_OUTCOMES TABLE POLICIES
-- - SELECT: All tenant members.
-- - INSERT/UPDATE: Operators, admins, and owners.
-- ============================================================================

DROP POLICY IF EXISTS "recovery_outcomes_select_tenant" ON recovery_outcomes;
CREATE POLICY "recovery_outcomes_select_tenant"
    ON recovery_outcomes FOR SELECT
    TO authenticated
    USING (public.is_merchant_member(merchant_id));

DROP POLICY IF EXISTS "recovery_outcomes_insert_operator" ON recovery_outcomes;
CREATE POLICY "recovery_outcomes_insert_operator"
    ON recovery_outcomes FOR INSERT
    TO authenticated
    WITH CHECK (public.is_merchant_operator_or_above(merchant_id));

DROP POLICY IF EXISTS "recovery_outcomes_update_operator" ON recovery_outcomes;
CREATE POLICY "recovery_outcomes_update_operator"
    ON recovery_outcomes FOR UPDATE
    TO authenticated
    USING (public.is_merchant_operator_or_above(merchant_id))
    WITH CHECK (public.is_merchant_operator_or_above(merchant_id));

-- ============================================================================
-- 12. ACTION_STATISTICS TABLE POLICIES
-- - SELECT: All tenant members.
-- - INSERT/UPDATE: Operators, admins, and owners.
-- ============================================================================

DROP POLICY IF EXISTS "action_statistics_select_tenant" ON action_statistics;
CREATE POLICY "action_statistics_select_tenant"
    ON action_statistics FOR SELECT
    TO authenticated
    USING (public.is_merchant_member(merchant_id));

DROP POLICY IF EXISTS "action_statistics_insert_operator" ON action_statistics;
CREATE POLICY "action_statistics_insert_operator"
    ON action_statistics FOR INSERT
    TO authenticated
    WITH CHECK (public.is_merchant_operator_or_above(merchant_id));

DROP POLICY IF EXISTS "action_statistics_update_operator" ON action_statistics;
CREATE POLICY "action_statistics_update_operator"
    ON action_statistics FOR UPDATE
    TO authenticated
    USING (public.is_merchant_operator_or_above(merchant_id))
    WITH CHECK (public.is_merchant_operator_or_above(merchant_id));

-- ============================================================================
-- 13. BASELINE_RESULTS TABLE POLICIES
-- - SELECT: All tenant members.
-- - INSERT/UPDATE: Operators, admins, and owners.
-- ============================================================================

DROP POLICY IF EXISTS "baseline_results_select_tenant" ON baseline_results;
CREATE POLICY "baseline_results_select_tenant"
    ON baseline_results FOR SELECT
    TO authenticated
    USING (public.is_merchant_member(merchant_id));

DROP POLICY IF EXISTS "baseline_results_insert_operator" ON baseline_results;
CREATE POLICY "baseline_results_insert_operator"
    ON baseline_results FOR INSERT
    TO authenticated
    WITH CHECK (public.is_merchant_operator_or_above(merchant_id));

DROP POLICY IF EXISTS "baseline_results_update_operator" ON baseline_results;
CREATE POLICY "baseline_results_update_operator"
    ON baseline_results FOR UPDATE
    TO authenticated
    USING (public.is_merchant_operator_or_above(merchant_id))
    WITH CHECK (public.is_merchant_operator_or_above(merchant_id));

-- ============================================================================
-- 14. AUDIT_LOGS TABLE POLICIES
-- - SELECT: All tenant members.
-- - INSERT: Operators, admins, and owners (and server-side processes).
-- - UPDATE/DELETE: Explicitly disallowed (immutable append-only audit trail).
-- ============================================================================

DROP POLICY IF EXISTS "audit_logs_select_tenant" ON audit_logs;
CREATE POLICY "audit_logs_select_tenant"
    ON audit_logs FOR SELECT
    TO authenticated
    USING (public.is_merchant_member(merchant_id));

DROP POLICY IF EXISTS "audit_logs_insert_operator" ON audit_logs;
CREATE POLICY "audit_logs_insert_operator"
    ON audit_logs FOR INSERT
    TO authenticated
    WITH CHECK (public.is_merchant_operator_or_above(merchant_id));

-- Immutable: No UPDATE or DELETE policies created for audit_logs.
