import { HealthStatus, RecoveryMetrics, RecoveryCase, CaseDetail, BatchRunResult } from '../types';
import { UserProfile } from '../auth/types';

const rawBaseUrl = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000';
const API_BASE_URL = rawBaseUrl.replace(/\/+$/, '');

async function handleResponse<T>(response: Response): Promise<T> {
  if (!response.ok) {
    let errorDetail = `Request failed (${response.status})`;
    try {
      const errData = await response.json();
      if (errData && errData.detail) {
        errorDetail = errData.detail;
      }
    } catch {
      // ignore json parse error
    }
    throw new Error(errorDetail);
  }
  return response.json();
}

export async function fetchHealth(): Promise<HealthStatus> {
  const response = await fetch(`${API_BASE_URL}/health`);
  return handleResponse<HealthStatus>(response);
}

export async function fetchMe(token: string): Promise<UserProfile> {
  const response = await fetch(`${API_BASE_URL}/api/v1/auth/me`, {
    headers: {
      Authorization: `Bearer ${token}`,
      Accept: 'application/json',
    },
  });
  return handleResponse<UserProfile>(response);
}

export async function fetchRecoveryMetrics(token: string, batchId?: string): Promise<RecoveryMetrics> {
  const url = new URL(`${API_BASE_URL}/api/v1/recovery/metrics`);
  if (batchId && batchId !== 'ALL') {
    url.searchParams.set('batch_id', batchId);
  }

  const response = await fetch(url.toString(), {
    headers: {
      Authorization: `Bearer ${token}`,
      Accept: 'application/json',
    },
  });
  return handleResponse<RecoveryMetrics>(response);
}

export async function fetchRecoveryCases(token: string, status?: string, batchId?: string): Promise<RecoveryCase[]> {
  const url = new URL(`${API_BASE_URL}/api/v1/recovery/cases`);
  if (status && status !== 'ALL') {
    url.searchParams.set('status', status);
  }
  if (batchId && batchId !== 'ALL') {
    url.searchParams.set('batch_id', batchId);
  }

  const response = await fetch(url.toString(), {
    headers: {
      Authorization: `Bearer ${token}`,
      Accept: 'application/json',
    },
  });
  return handleResponse<RecoveryCase[]>(response);
}

export async function fetchCaseDetail(token: string, caseId: string): Promise<CaseDetail> {
  const response = await fetch(`${API_BASE_URL}/api/v1/recovery/cases/${caseId}`, {
    headers: {
      Authorization: `Bearer ${token}`,
      Accept: 'application/json',
    },
  });
  return handleResponse<CaseDetail>(response);
}

export async function runNextCaseStep(token: string, caseId: string): Promise<RecoveryCase> {
  const response = await fetch(`${API_BASE_URL}/api/v1/recovery/cases/${caseId}/run`, {
    method: 'POST',
    headers: {
      Authorization: `Bearer ${token}`,
      Accept: 'application/json',
    },
  });
  return handleResponse<RecoveryCase>(response);
}

export async function seedDemoBatch(token: string): Promise<BatchRunResult> {
  const response = await fetch(`${API_BASE_URL}/api/v1/recovery/seed-demo-batch`, {
    method: 'POST',
    headers: {
      Authorization: `Bearer ${token}`,
      Accept: 'application/json',
    },
  });
  return handleResponse<BatchRunResult>(response);
}
