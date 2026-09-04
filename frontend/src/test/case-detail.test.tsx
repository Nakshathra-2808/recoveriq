import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { CaseDetailModal } from '../components/recovery/CaseDetailModal';
import { CaseDetail } from '../types';

const mockLLMCase: CaseDetail = {
  id: 'case-llm-1234',
  merchant_id: '00000000-0000-0000-0000-000000000001',
  payment_id: 'pay_demo_001',
  customer_id: 'cust-1',
  customer_name: 'Aarav Sharma',
  customer_email: 'aarav.sharma@example.com',
  amount: 2499.0,
  currency: 'INR',
  status: 'APPROVED',
  priority: 'MEDIUM',
  retry_count: 0,
  communication_count: 0,
  recovered_amount: 0.0,
  diagnosis_summary: {
    source: 'LLM',
    failure_type: 'NETWORK_TIMEOUT',
    recommended_action: 'RETRY_LATER',
    confidence: 0.94,
    reason: 'Similar network timeout cases historically recover better after a delayed retry.',
  },
  actions: [
    {
      id: 'act-1',
      case_id: 'case-llm-1234',
      action_type: 'RETRY_LATER',
      execution_mode: 'SIMULATION',
      status: 'COMPLETED',
      sequence_number: 1,
      payload: {},
      guardrail_check_passed: true,
      ai_confidence_score: 0.94,
      ai_reasoning: 'Delayed retry scheduled.',
      created_at: '2026-09-04T12:00:00Z',
    },
  ],
  outcomes: [],
  audit_logs: [
    {
      id: 'log-1',
      case_id: 'case-llm-1234',
      actor_type: 'AI_AGENT',
      event_type: 'FAILURE_DIAGNOSED',
      severity: 'INFO',
      description: 'AI diagnosis (LLM): NETWORK_TIMEOUT -> RETRY_LATER (Confidence: 94.0%)',
      details: {},
      created_at: '2026-09-04T12:00:00Z',
    },
  ],
  created_at: '2026-09-04T12:00:00Z',
  updated_at: '2026-09-04T12:00:00Z',
};

const mockFallbackCase: CaseDetail = {
  id: 'case-fallback-5678',
  merchant_id: '00000000-0000-0000-0000-000000000001',
  payment_id: 'pay_demo_006',
  customer_id: 'cust-6',
  customer_name: 'Ananya Roy (Opted Out)',
  customer_email: 'ananya.roy@example.com',
  amount: 4999.0,
  currency: 'INR',
  status: 'STOPPED',
  priority: 'HIGH',
  retry_count: 0,
  communication_count: 0,
  recovered_amount: 0.0,
  diagnosis_summary: {
    source: 'DETERMINISTIC_FALLBACK',
    failure_type: 'FRAUD_DECLINE',
    recommended_action: 'STOP',
    confidence: 0.98,
    reason: 'High-risk fraud decline flagged. Automated retries strictly prohibited.',
  },
  actions: [
    {
      id: 'act-6',
      case_id: 'case-fallback-5678',
      action_type: 'STOP',
      execution_mode: 'SIMULATION',
      status: 'COMPLETED',
      sequence_number: 1,
      payload: {},
      guardrail_check_passed: true,
      ai_confidence_score: 0.98,
      ai_reasoning: 'Terminal stop.',
      created_at: '2026-09-04T12:00:00Z',
    },
  ],
  outcomes: [],
  audit_logs: [],
  created_at: '2026-09-04T12:00:00Z',
  updated_at: '2026-09-04T12:00:00Z',
};

describe('CaseDetailModal AI Diagnosis & Decision Flow UI', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it('renders LLM-powered AI diagnosis with confidence, reason, and LLM badge', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValueOnce({
      ok: true,
      json: async () => mockLLMCase,
    } as Response);

    render(
      <CaseDetailModal
        caseId="case-llm-1234"
        token="test-token"
        onClose={() => {}}
        onCaseUpdated={() => {}}
      />
    );

    await waitFor(() => {
      expect(screen.getByText(/AI DIAGNOSIS & REASONING/i)).toBeDefined();
    });

    // Check LLM badge and details
    expect(screen.getAllByText('LLM').length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText('NETWORK_TIMEOUT')).toBeDefined();
    expect(screen.getAllByText('RETRY_LATER').length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText('94%')).toBeDefined();
    expect(
      screen.getByText(/Similar network timeout cases historically recover better after a delayed retry/i)
    ).toBeDefined();

    // Check 4-Stage Decision Flow
    expect(screen.getByText(/1\. AI Recommends/i)).toBeDefined();
    expect(screen.getByText(/2\. Policy Evaluates/i)).toBeDefined();
    expect(screen.getByText(/3\. Guardrail Decides/i)).toBeDefined();
    expect(screen.getByText(/4\. Executor Acts/i)).toBeDefined();
    expect(screen.getByText(/✓ PASSED/i)).toBeDefined();
  });

  it('renders DETERMINISTIC FALLBACK when offline or rule-based analysis is used', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValueOnce({
      ok: true,
      json: async () => mockFallbackCase,
    } as Response);

    render(
      <CaseDetailModal
        caseId="case-fallback-5678"
        token="test-token"
        onClose={() => {}}
        onCaseUpdated={() => {}}
      />
    );

    await waitFor(() => {
      expect(screen.getByText(/AI DIAGNOSIS & REASONING/i)).toBeDefined();
    });

    // Check Fallback badge
    expect(screen.getAllByText('DETERMINISTIC FALLBACK').length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText('FRAUD_DECLINE')).toBeDefined();
    expect(screen.getAllByText('STOP').length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText('98%')).toBeDefined();

    // Check Guardrail STOPPED decision
    expect(screen.getByText(/🛑 STOPPED/i)).toBeDefined();
  });
});
