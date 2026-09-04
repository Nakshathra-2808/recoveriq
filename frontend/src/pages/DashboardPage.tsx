import React, { useEffect, useState, useCallback } from 'react';
import {
  RotateCw,
  AlertCircle,
  CheckCircle2,
  Building,
  RefreshCw,
  Play,
  TrendingUp,
  Layers,
  History,
} from 'lucide-react';
import { useAuth } from '../auth/AuthContext';
import { fetchRecoveryMetrics, fetchRecoveryCases, seedDemoBatch, runNextCaseStep } from '../services/api';
import { RecoveryMetrics, RecoveryCase, BatchRunResult } from '../types';
import { MetricsCards } from '../components/recovery/MetricsCards';
import { RecoveryCasesTable } from '../components/recovery/RecoveryCasesTable';
import { CaseDetailModal } from '../components/recovery/CaseDetailModal';
import { SimulationBanner } from '../components/recovery/SimulationBanner';

export const DashboardPage: React.FC = () => {
  const { session, profile, refreshProfile } = useAuth();

  const [metrics, setMetrics] = useState<RecoveryMetrics | null>(null);
  const [cases, setCases] = useState<RecoveryCase[]>([]);
  const [activeBatchId, setActiveBatchId] = useState<string | 'ALL'>('ALL');
  const [latestBatchId, setLatestBatchId] = useState<string | null>(null);

  const [loadingMetrics, setLoadingMetrics] = useState<boolean>(true);
  const [loadingCases, setLoadingCases] = useState<boolean>(true);
  const [runningDemo, setRunningDemo] = useState<boolean>(false);
  const [runningCaseId, setRunningCaseId] = useState<string | null>(null);

  const [selectedCaseId, setSelectedCaseId] = useState<string | null>(null);
  const [notification, setNotification] = useState<{ type: 'success' | 'error'; message: string } | null>(null);

  const token = session?.access_token || '';

  // 1. Fetch Metrics & Cases with Batch Scoping
  const loadDashboardData = useCallback(async (authToken: string, batchScope?: string) => {
    if (!authToken) return;

    const targetBatch = batchScope !== undefined ? batchScope : activeBatchId;

    // Fetch Metrics
    setLoadingMetrics(true);
    fetchRecoveryMetrics(authToken, targetBatch === 'ALL' ? undefined : targetBatch)
      .then((data) => {
        setMetrics(data);
      })
      .catch((err) => {
        console.error('Failed to load recovery metrics:', err);
      })
      .finally(() => {
        setLoadingMetrics(false);
      });

    // Fetch Cases
    setLoadingCases(true);
    fetchRecoveryCases(authToken, undefined, targetBatch === 'ALL' ? undefined : targetBatch)
      .then((data) => {
        setCases(data);
      })
      .catch((err) => {
        console.error('Failed to load recovery cases:', err);
      })
      .finally(() => {
        setLoadingCases(false);
      });
  }, [activeBatchId]);

  useEffect(() => {
    if (token) {
      loadDashboardData(token);
    }
  }, [token, loadDashboardData]);

  // 2. Execute Demo Batch
  const handleRunDemoBatch = async () => {
    if (!token) return;
    try {
      setRunningDemo(true);
      setNotification(null);
      const result: BatchRunResult = await seedDemoBatch(token);
      
      setLatestBatchId(result.batch_id);
      setActiveBatchId(result.batch_id);

      setNotification({
        type: 'success',
        message: `Demo Batch executed successfully! Processed ${result.total_records} transactions, recovered ₹${result.total_recovered_amount.toFixed(2)} (${result.recovery_lift_percentage.toFixed(1)}% lift vs baseline).`,
      });

      // Automatically refresh metrics and cases scoped to this new batch
      await loadDashboardData(token, result.batch_id);
    } catch (err: any) {
      setNotification({
        type: 'error',
        message: err.message || 'Failed to run demo recovery batch',
      });
    } finally {
      setRunningDemo(false);
    }
  };

  // Switch Batch Scope Filter
  const handleScopeChange = (newScope: string | 'ALL') => {
    setActiveBatchId(newScope);
    if (token) {
      loadDashboardData(token, newScope);
    }
  };

  // 3. Run Single Case Next Step
  const handleRunCaseStep = async (caseId: string) => {
    if (!token) return;
    try {
      setRunningCaseId(caseId);
      setNotification(null);
      const updated = await runNextCaseStep(token, caseId);
      setNotification({
        type: 'success',
        message: `Advanced case ${caseId.slice(0, 8)}... to ${updated.status}. Recovered: ₹${updated.recovered_amount.toFixed(2)}`,
      });
      // Update local state and refresh metrics
      setCases((prev) => prev.map((c) => (c.id === caseId ? updated : c)));
      fetchRecoveryMetrics(token, activeBatchId === 'ALL' ? undefined : activeBatchId).then((data) => setMetrics(data));
    } catch (err: any) {
      setNotification({
        type: 'error',
        message: err.message || 'Failed to run case recovery step',
      });
    } finally {
      setRunningCaseId(null);
    }
  };

  const handleCaseUpdated = (updatedCase: RecoveryCase) => {
    setCases((prev) => prev.map((c) => (c.id === updatedCase.id ? updatedCase : c)));
    if (token) {
      fetchRecoveryMetrics(token, activeBatchId === 'ALL' ? undefined : activeBatchId).then((data) => setMetrics(data));
    }
  };

  const isLatestBatchActive = activeBatchId !== 'ALL' && activeBatchId === latestBatchId;

  return (
    <div className="space-y-6 max-w-7xl mx-auto pb-12">
      {/* Top Banner / Merchant Workspace & Demo Action */}
      <div className="bg-slate-900 border border-slate-800 rounded-2xl p-6 sm:p-7 shadow-xl relative overflow-hidden">
        <div className="flex flex-col lg:flex-row lg:items-center lg:justify-between gap-5">
          <div className="space-y-1.5">
            <div className="flex flex-wrap items-center gap-2">
              <span className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full bg-indigo-950/90 border border-indigo-700/50 text-indigo-300 text-xs font-semibold uppercase tracking-wider">
                <span className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse" />
                Stage 3: Core Recovery Console
              </span>
              <span className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full bg-slate-950 border border-slate-800 text-slate-400 text-xs">
                <Building className="w-3.5 h-3.5 text-indigo-400" />
                {profile?.merchant_name || 'Acme Retail India'} ({profile?.role || 'operator'})
              </span>
            </div>
            <h1 className="text-2xl sm:text-3xl font-extrabold text-slate-100 tracking-tight">
              Adaptive Revenue Recovery Agent
            </h1>
            <p className="text-slate-400 text-xs sm:text-sm max-w-2xl">
              Closed-loop payment recovery engine powered by Bayesian action scoring, deterministic safety guardrails, verifiable simulation outcomes, and continuous learning.
            </p>
          </div>

          <div className="flex flex-wrap items-center gap-3 shrink-0">
            {/* Run Demo Recovery Button */}
            <button
              onClick={handleRunDemoBatch}
              disabled={runningDemo || !token}
              className="px-5 py-3 rounded-xl bg-gradient-to-r from-indigo-600 via-indigo-500 to-indigo-600 hover:from-indigo-500 hover:to-indigo-500 text-white text-sm font-bold shadow-xl shadow-indigo-600/30 transition-all flex items-center gap-2.5 disabled:opacity-50 cursor-pointer active:scale-95"
            >
              {runningDemo ? (
                <>
                  <RotateCw className="w-4 h-4 animate-spin" />
                  <span>Executing 9-Stage Recovery Engine...</span>
                </>
              ) : (
                <>
                  <Play className="w-4 h-4 fill-current" />
                  <span>Run Demo Recovery</span>
                </>
              )}
            </button>

            {/* Refresh Button */}
            <button
              onClick={() => {
                if (token) loadDashboardData(token);
                refreshProfile();
              }}
              className="p-3 rounded-xl bg-slate-800 hover:bg-slate-700 text-slate-300 text-xs transition-colors border border-slate-700 cursor-pointer"
              title="Refresh all metrics and cases"
            >
              <RefreshCw className="w-4 h-4" />
            </button>
          </div>
        </div>
      </div>

      {/* Execution Mode Notice */}
      <SimulationBanner />

      {/* Notification Toast */}
      {notification && (
        <div
          className={`p-4 rounded-xl border text-xs sm:text-sm flex items-start justify-between gap-3 shadow-lg transition-all ${
            notification.type === 'success'
              ? 'bg-emerald-950/50 border-emerald-500/40 text-emerald-200'
              : 'bg-rose-950/50 border-rose-500/40 text-rose-200'
          }`}
        >
          <div className="flex items-center gap-2">
            {notification.type === 'success' ? (
              <CheckCircle2 className="w-5 h-5 text-emerald-400 shrink-0" />
            ) : (
              <AlertCircle className="w-5 h-5 text-rose-400 shrink-0" />
            )}
            <span>{notification.message}</span>
          </div>
          <button
            onClick={() => setNotification(null)}
            className="text-slate-400 hover:text-slate-200 text-xs font-semibold cursor-pointer"
          >
            Dismiss
          </button>
        </div>
      )}

      {/* Real Metric Cards with Scope Selector */}
      <div className="space-y-3">
        <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 bg-slate-900/60 border border-slate-800/80 rounded-xl px-4 py-3">
          <div className="flex items-center gap-2">
            <TrendingUp className="w-4 h-4 text-indigo-400" />
            <span className="text-sm font-bold text-slate-200">
              Recovery Benchmark Metrics {isLatestBatchActive ? '(Latest Demo Batch)' : activeBatchId !== 'ALL' ? `(Batch #${activeBatchId.slice(0, 8)})` : '(All Historical Batches)'}
            </span>
          </div>

          <div className="flex items-center gap-1.5 bg-slate-950 p-1 rounded-lg border border-slate-800 text-xs">
            {latestBatchId && (
              <button
                onClick={() => handleScopeChange(latestBatchId)}
                className={`px-3 py-1 rounded-md font-semibold transition-colors cursor-pointer flex items-center gap-1.5 ${
                  activeBatchId === latestBatchId
                    ? 'bg-indigo-600 text-white shadow-sm'
                    : 'text-slate-400 hover:text-slate-200'
                }`}
              >
                <Layers className="w-3.5 h-3.5" />
                Latest Batch
              </button>
            )}
            <button
              onClick={() => handleScopeChange('ALL')}
              className={`px-3 py-1 rounded-md font-semibold transition-colors cursor-pointer flex items-center gap-1.5 ${
                activeBatchId === 'ALL'
                  ? 'bg-indigo-600 text-white shadow-sm'
                  : 'text-slate-400 hover:text-slate-200'
              }`}
            >
              <History className="w-3.5 h-3.5" />
              All Batches (Lifetime)
            </button>
          </div>
        </div>

        <MetricsCards metrics={metrics} loading={loadingMetrics} />
      </div>

      {/* Recovery Cases Table */}
      <RecoveryCasesTable
        cases={cases}
        loading={loadingCases}
        onSelectCase={(caseId) => setSelectedCaseId(caseId)}
        onRunCaseStep={handleRunCaseStep}
        runningCaseId={runningCaseId}
      />

      {/* Case Details / 9-Stage Timeline Modal */}
      {selectedCaseId && token && (
        <CaseDetailModal
          caseId={selectedCaseId}
          token={token}
          onClose={() => setSelectedCaseId(null)}
          onCaseUpdated={handleCaseUpdated}
        />
      )}
    </div>
  );
};
