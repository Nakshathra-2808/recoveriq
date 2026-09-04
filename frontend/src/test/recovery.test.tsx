import { describe, it, expect, vi, beforeEach } from 'vitest';
import {
  fetchHealth,
  fetchMe,
  fetchRecoveryMetrics,
  fetchRecoveryCases,
  fetchCaseDetail,
  runNextCaseStep,
  seedDemoBatch,
} from '../services/api';
import { RecoveryMetrics, RecoveryCase, CaseDetail, BatchRunResult } from '../types';

const MOCK_TOKEN = 'mock-jwt-supabase-access-token';

const mockMetrics: RecoveryMetrics = {
  merchant_id: '00000000-0000-0000-0000-000000000001',
  total_revenue_at_risk: 35948.0,
  recoveriq_recovered_revenue: 25198.0,
  baseline_recovered_revenue: 8748.0,
  incremental_revenue_recovered: 16450.0,
  recovery_lift_percentage: 188.04,
  total_cases_processed: 6,
  total_cases_recovered: 4,
  overall_recovery_rate: 0.6667,
  success_rate_by_category: {
    NETWORK_TIMEOUT: 0.85,
    GATEWAY_ERROR: 0.8,
  },
  top_recovery_actions: [],
};

const mockCases: RecoveryCase[] = [
  {
    id: 'case-1111-2222',
    merchant_id: '00000000-0000-0000-0000-000000000001',
    payment_id: 'pay_syn_001',
    customer_id: 'cust-1',
    customer_name: 'Aarav Sharma',
    customer_email: 'aarav.sharma@example.com',
    amount: 2499.0,
    currency: 'INR',
    status: 'RECOVERED',
    priority: 'MEDIUM',
    retry_count: 1,
    communication_count: 0,
    recovered_amount: 2499.0,
    diagnosis_summary: {
      root_cause_category: 'NETWORK_TIMEOUT',
      confidence_score: 0.94,
      reasoning: 'Transient connection timeout',
    },
    created_at: '2026-09-04T12:00:00Z',
    updated_at: '2026-09-04T12:01:00Z',
    resolved_at: '2026-09-04T12:01:00Z',
  },
  {
    id: 'case-3333-4444',
    merchant_id: '00000000-0000-0000-0000-000000000001',
    payment_id: 'pay_syn_002',
    customer_id: 'cust-2',
    customer_name: 'Vikram Singh (VIP)',
    customer_email: 'vikram.singh@example.com',
    amount: 14500.0,
    currency: 'INR',
    status: 'ESCALATED',
    priority: 'HIGH',
    retry_count: 0,
    communication_count: 0,
    recovered_amount: 0.0,
    diagnosis_summary: {
      root_cause_category: 'CARD_LIMIT_EXCEEDED',
      confidence_score: 0.9,
    },
    created_at: '2026-09-04T12:00:00Z',
    updated_at: '2026-09-04T12:01:00Z',
  },
];

const mockBatchResult: BatchRunResult = {
  batch_id: 'batch-9999',
  merchant_id: '00000000-0000-0000-0000-000000000001',
  name: 'Acme Retail Demo Recovery Batch',
  status: 'COMPLETED',
  total_records: 6,
  processed_records: 6,
  recovered_records: 4,
  total_amount_at_risk: 35948.0,
  total_recovered_amount: 25198.0,
  recovery_rate: 0.6667,
  baseline_recovered_amount: 8748.0,
  incremental_revenue: 16450.0,
  recovery_lift_percentage: 188.04,
  cases: mockCases,
};

describe('RecoverIQ Frontend API Client & Recovery Engine Services', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  // 1. Authenticated API Request & Headers
  it('sends the Authorization Bearer token on authenticated endpoints', async () => {
    const fetchSpy = vi.spyOn(globalThis, 'fetch').mockResolvedValueOnce({
      ok: true,
      json: async () => ({
        user_id: 'usr-1',
        email: 'merchant@acmeretail.example.com',
        merchant_id: '00000000-0000-0000-0000-000000000001',
        merchant_name: 'Acme Retail India',
        role: 'operator',
      }),
    } as Response);

    const profile = await fetchMe(MOCK_TOKEN);

    expect(fetchSpy).toHaveBeenCalledWith(
      expect.stringContaining('/api/v1/auth/me'),
      expect.objectContaining({
        headers: expect.objectContaining({
          Authorization: `Bearer ${MOCK_TOKEN}`,
        }),
      })
    );
    expect(profile.email).toBe('merchant@acmeretail.example.com');
    expect(profile.merchant_name).toBe('Acme Retail India');
  });

  // 2. Metrics Loading (Global and Batch-Scoped)
  it('loads recovery benchmark metrics with correct structure and supports batch_id scoping', async () => {
    const fetchSpy = vi.spyOn(globalThis, 'fetch').mockResolvedValueOnce({
      ok: true,
      json: async () => mockMetrics,
    } as Response);

    const metrics = await fetchRecoveryMetrics(MOCK_TOKEN, 'batch-9999');

    expect(fetchSpy).toHaveBeenCalledWith(
      expect.stringContaining('/api/v1/recovery/metrics?batch_id=batch-9999'),
      expect.anything()
    );
    expect(metrics.total_revenue_at_risk).toBe(35948.0);
    expect(metrics.recoveriq_recovered_revenue).toBe(25198.0);
    expect(metrics.incremental_revenue_recovered).toBe(16450.0);
    expect(metrics.recovery_lift_percentage).toBe(188.04);
  });

  // 3. Cases Loading (with Status and Batch filters)
  it('loads recovery cases list with optional status and batch filters', async () => {
    const fetchSpy = vi.spyOn(globalThis, 'fetch').mockResolvedValueOnce({
      ok: true,
      json: async () => mockCases,
    } as Response);

    const cases = await fetchRecoveryCases(MOCK_TOKEN, 'RECOVERED', 'batch-9999');

    expect(fetchSpy).toHaveBeenCalledWith(
      expect.stringContaining('status=RECOVERED'),
      expect.anything()
    );
    expect(fetchSpy).toHaveBeenCalledWith(
      expect.stringContaining('batch_id=batch-9999'),
      expect.anything()
    );
    expect(cases).toHaveLength(2);
    expect(cases[0].customer_name).toBe('Aarav Sharma');
    expect(cases[0].recovered_amount).toBe(2499.0);
  });

  // 4. Demo Batch Execution
  it('executes demo recovery batch and returns processed results', async () => {
    const fetchSpy = vi.spyOn(globalThis, 'fetch').mockResolvedValueOnce({
      ok: true,
      json: async () => mockBatchResult,
    } as Response);

    const batch = await seedDemoBatch(MOCK_TOKEN);

    expect(fetchSpy).toHaveBeenCalledWith(
      expect.stringContaining('/api/v1/recovery/seed-demo-batch'),
      expect.objectContaining({
        method: 'POST',
        headers: expect.objectContaining({
          Authorization: `Bearer ${MOCK_TOKEN}`,
        }),
      })
    );
    expect(batch.status).toBe('COMPLETED');
    expect(batch.total_records).toBe(6);
    expect(batch.total_recovered_amount).toBe(25198.0);
  });

  // 5. Single Case Run Next Step
  it('advances a single case recovery cycle', async () => {
    const fetchSpy = vi.spyOn(globalThis, 'fetch').mockResolvedValueOnce({
      ok: true,
      json: async () => mockCases[0],
    } as Response);

    const updatedCase = await runNextCaseStep(MOCK_TOKEN, 'case-1111-2222');

    expect(fetchSpy).toHaveBeenCalledWith(
      expect.stringContaining('/api/v1/recovery/cases/case-1111-2222/run'),
      expect.objectContaining({
        method: 'POST',
        headers: expect.objectContaining({
          Authorization: `Bearer ${MOCK_TOKEN}`,
        }),
      })
    );
    expect(updatedCase.status).toBe('RECOVERED');
  });

  // 6. Case Detail & Timeline
  it('loads full 9-stage case detail, actions, outcomes, and audit logs', async () => {
    const mockDetail: CaseDetail = {
      ...mockCases[0],
      actions: [
        {
          id: 'act-1',
          case_id: 'case-1111-2222',
          action_type: 'RETRY_NOW',
          execution_mode: 'SIMULATION',
          status: 'COMPLETED',
          sequence_number: 1,
          payload: { retry_amount: 2499.0 },
          guardrail_check_passed: true,
          created_at: '2026-09-04T12:00:10Z',
        },
      ],
      outcomes: [
        {
          id: 'out-1',
          case_id: 'case-1111-2222',
          action_id: 'act-1',
          outcome_type: 'RECOVERED',
          is_successful: true,
          recovered_amount: 2499.0,
          new_payment_id: 'pay_sim_001_abc123',
          recorded_at: '2026-09-04T12:00:55Z',
        },
      ],
      audit_logs: [
        {
          id: 'log-1',
          case_id: 'case-1111-2222',
          actor_type: 'SYSTEM',
          event_type: 'CASE_DETECTED',
          severity: 'INFO',
          description: 'Recovery case detected for failed payment',
          details: {},
          created_at: '2026-09-04T12:00:00Z',
        },
      ],
    };

    vi.spyOn(globalThis, 'fetch').mockResolvedValueOnce({
      ok: true,
      json: async () => mockDetail,
    } as Response);

    const detail = await fetchCaseDetail(MOCK_TOKEN, 'case-1111-2222');

    expect(detail.actions).toHaveLength(1);
    expect(detail.actions[0].action_type).toBe('RETRY_NOW');
    expect(detail.actions[0].execution_mode).toBe('SIMULATION');
    expect(detail.outcomes).toHaveLength(1);
    expect(detail.outcomes[0].is_successful).toBe(true);
    expect(detail.audit_logs).toHaveLength(1);
  });

  // 7. Error Handling
  it('throws structured error message on API 401 or 500 responses', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValueOnce({
      ok: false,
      status: 401,
      json: async () => ({ detail: 'Invalid authentication token: Signature has expired' }),
    } as Response);

    await expect(fetchRecoveryMetrics(MOCK_TOKEN)).rejects.toThrow(
      'Invalid authentication token: Signature has expired'
    );
  });

  it('handles health check endpoint', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValueOnce({
      ok: true,
      json: async () => ({ status: 'ok', service: 'recoveriq-backend', version: '0.1.0' }),
    } as Response);

    const health = await fetchHealth();
    expect(health.status).toBe('ok');
    expect(health.service).toBe('recoveriq-backend');
  });
});
