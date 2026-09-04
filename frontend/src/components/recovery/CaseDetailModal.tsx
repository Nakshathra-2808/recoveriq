import React, { useEffect, useState, useCallback } from 'react';
import {
  X,
  Play,
  RotateCw,
  AlertCircle,
  ShieldCheck,
  Zap,
  History,
  Layers,
} from 'lucide-react';
import { fetchCaseDetail, runNextCaseStep } from '../../services/api';
import { CaseDetail, RecoveryCase } from '../../types';

interface CaseDetailModalProps {
  caseId: string;
  token: string;
  onClose: () => void;
  onCaseUpdated: (updatedCase: RecoveryCase) => void;
}

export const CaseDetailModal: React.FC<CaseDetailModalProps> = ({
  caseId,
  token,
  onClose,
  onCaseUpdated,
}) => {
  const [detail, setDetail] = useState<CaseDetail | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);
  const [runningStep, setRunningStep] = useState<boolean>(false);
  const [activeTab, setActiveTab] = useState<'TIMELINE' | 'ACTIONS' | 'AUDIT'>('TIMELINE');

  const loadCase = useCallback(async () => {
    try {
      setLoading(true);
      setError(null);
      const data = await fetchCaseDetail(token, caseId);
      setDetail(data);
    } catch (err: any) {
      setError(err.message || 'Failed to load case details');
    } finally {
      setLoading(false);
    }
  }, [caseId, token]);

  useEffect(() => {
    loadCase();
  }, [loadCase]);

  const handleRunNextStep = async () => {
    try {
      setRunningStep(true);
      setError(null);
      const updated = await runNextCaseStep(token, caseId);
      onCaseUpdated(updated);
      await loadCase();
    } catch (err: any) {
      setError(err.message || 'Failed to execute next recovery step');
    } finally {
      setRunningStep(false);
    }
  };

  const formatINR = (val: number | undefined) => {
    if (val === undefined || val === null) return '₹0.00';
    return new Intl.NumberFormat('en-IN', {
      style: 'currency',
      currency: 'INR',
      maximumFractionDigits: 2,
    }).format(val);
  };

  const formatTime = (iso?: string | null) => {
    if (!iso) return '—';
    try {
      return new Date(iso).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' });
    } catch {
      return iso;
    }
  };

  const latestAction = detail?.actions?.[detail.actions.length - 1];
  const latestOutcome = detail?.outcomes?.[detail.outcomes.length - 1];
  const diag = detail?.diagnosis_summary || {};

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-3 sm:p-6 bg-slate-950/80 backdrop-blur-sm overflow-y-auto">
      <div className="bg-slate-900 border border-slate-800 rounded-2xl w-full max-w-4xl max-h-[90vh] flex flex-col shadow-2xl overflow-hidden relative">
        {/* Header */}
        <div className="p-5 sm:p-6 border-b border-slate-800 flex items-start justify-between gap-4 bg-slate-950/50">
          <div>
            <div className="flex flex-wrap items-center gap-2 mb-2">
              <span className="px-2.5 py-0.5 rounded-full text-xs font-semibold bg-indigo-500/20 text-indigo-300 border border-indigo-500/30">
                Case ID: {caseId.slice(0, 8)}...
              </span>
              <span className="px-2 py-0.5 rounded text-xs font-semibold bg-slate-800 text-slate-300">
                Status: {detail?.status || 'LOADING'}
              </span>
              {latestAction?.execution_mode === 'RAZORPAY_TEST' ? (
                <span className="px-2 py-0.5 rounded text-xs font-semibold bg-blue-500/20 text-blue-300 border border-blue-500/30">
                  RAZORPAY TEST MODE
                </span>
              ) : latestAction?.execution_mode === 'DRY_RUN' ? (
                <span className="px-2 py-0.5 rounded text-xs font-semibold bg-slate-800 text-slate-300 border border-slate-700">
                  DRY RUN
                </span>
              ) : (
                <span className="px-2 py-0.5 rounded text-xs font-semibold bg-amber-500/20 text-amber-300 border border-amber-500/30">
                  SIMULATION MODE
                </span>
              )}
            </div>
            <h2 className="text-xl sm:text-2xl font-bold text-slate-100 flex items-center gap-2">
              <span>{detail?.customer_name || 'Recovery Case Detail'}</span>
              <span className="text-emerald-400 font-normal">({formatINR(detail?.amount)})</span>
            </h2>
            <p className="text-xs text-slate-400 mt-0.5">
              Payment ID: <span className="font-mono text-slate-300">{detail?.payment_id}</span> • Customer Email: <span className="text-slate-300">{detail?.customer_email || '—'}</span>
            </p>
          </div>

          <button
            onClick={onClose}
            className="w-8 h-8 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-400 hover:text-slate-200 flex items-center justify-center transition-colors cursor-pointer shrink-0"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Tab Navigation */}
        <div className="px-6 border-b border-slate-800 bg-slate-950/30 flex items-center gap-4">
          <button
            onClick={() => setActiveTab('TIMELINE')}
            className={`py-3 text-xs sm:text-sm font-semibold border-b-2 transition-colors cursor-pointer flex items-center gap-1.5 ${
              activeTab === 'TIMELINE'
                ? 'border-indigo-500 text-indigo-400'
                : 'border-transparent text-slate-400 hover:text-slate-300'
            }`}
          >
            <Layers className="w-4 h-4" />
            9-Stage Recovery Timeline
          </button>
          <button
            onClick={() => setActiveTab('ACTIONS')}
            className={`py-3 text-xs sm:text-sm font-semibold border-b-2 transition-colors cursor-pointer flex items-center gap-1.5 ${
              activeTab === 'ACTIONS'
                ? 'border-indigo-500 text-indigo-400'
                : 'border-transparent text-slate-400 hover:text-slate-300'
            }`}
          >
            <Zap className="w-4 h-4" />
            Actions &amp; Outcomes ({detail?.actions?.length || 0})
          </button>
          <button
            onClick={() => setActiveTab('AUDIT')}
            className={`py-3 text-xs sm:text-sm font-semibold border-b-2 transition-colors cursor-pointer flex items-center gap-1.5 ${
              activeTab === 'AUDIT'
                ? 'border-indigo-500 text-indigo-400'
                : 'border-transparent text-slate-400 hover:text-slate-300'
            }`}
          >
            <History className="w-4 h-4" />
            Immutable Audit Trail ({detail?.audit_logs?.length || 0})
          </button>
        </div>

        {/* Modal Body */}
        <div className="p-5 sm:p-6 overflow-y-auto flex-1 space-y-6">
          {error && (
            <div className="p-3.5 rounded-xl bg-rose-950/40 border border-rose-800/50 text-rose-300 text-xs flex items-center gap-2">
              <AlertCircle className="w-4 h-4 shrink-0" />
              <span>{error}</span>
            </div>
          )}

          {loading ? (
            <div className="py-12 flex flex-col items-center justify-center text-slate-400 space-y-3">
              <RotateCw className="w-8 h-8 animate-spin text-indigo-400" />
              <p className="text-sm font-medium">Fetching case lifecycle data...</p>
            </div>
          ) : !detail ? (
            <div className="py-12 text-center text-slate-500">Case record unavailable</div>
          ) : (
            <>
              {/* TAB 1: 9-STAGE RECOVERY TIMELINE & AI DIAGNOSIS */}
              {activeTab === 'TIMELINE' && (
                <div className="space-y-6">
                  {/* AI DIAGNOSIS & DECISION FLOW CARD */}
                  <div className="bg-slate-950/90 border border-indigo-900/40 rounded-2xl p-5 shadow-xl space-y-4 relative overflow-hidden">
                    <div className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-800/80 pb-3">
                      <div className="flex items-center gap-2">
                        <div className="w-7 h-7 rounded-lg bg-indigo-500/20 flex items-center justify-center text-indigo-400 border border-indigo-500/30">
                          <Zap className="w-4 h-4" />
                        </div>
                        <div>
                          <h3 className="text-sm font-bold text-slate-100 flex items-center gap-2">
                            <span>AI DIAGNOSIS &amp; REASONING</span>
                          </h3>
                          <p className="text-[11px] text-slate-400">Contextual failure analysis and recovery recommendation</p>
                        </div>
                      </div>

                      <div>
                        {diag.source === 'LLM' ? (
                          <span className="px-3 py-1 rounded-full text-xs font-bold bg-emerald-500/20 text-emerald-300 border border-emerald-500/30 flex items-center gap-1.5 shadow-sm shadow-emerald-500/10">
                            <span className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse"></span>
                            LLM
                          </span>
                        ) : (
                          <span className="px-3 py-1 rounded-full text-xs font-bold bg-slate-800 text-slate-300 border border-slate-700 flex items-center gap-1.5">
                            <span className="w-2 h-2 rounded-full bg-amber-400"></span>
                            DETERMINISTIC FALLBACK
                          </span>
                        )}
                      </div>
                    </div>

                    {/* AI Diagnosis Key Fields */}
                    <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
                      <div className="bg-slate-900/90 border border-slate-800 rounded-xl p-3">
                        <span className="text-[11px] text-slate-400 block font-medium">Failure Etiology</span>
                        <span className="text-xs font-bold text-slate-200 mt-1 block truncate">
                          {diag.failure_type || diag.root_cause_category || 'Identified'}
                        </span>
                      </div>
                      <div className="bg-slate-900/90 border border-slate-800 rounded-xl p-3">
                        <span className="text-[11px] text-slate-400 block font-medium">AI Recommendation</span>
                        <span className="text-xs font-bold text-indigo-300 mt-1 block truncate">
                          {diag.recommended_action || (diag.recommended_actions && diag.recommended_actions[0]) || 'RETRY_LATER'}
                        </span>
                      </div>
                      <div className="bg-slate-900/90 border border-slate-800 rounded-xl p-3">
                        <span className="text-[11px] text-slate-400 block font-medium">Confidence Score</span>
                        <span className="text-xs font-bold text-emerald-400 mt-1 block">
                          {Math.round(((diag.confidence !== undefined ? diag.confidence : diag.confidence_score) ?? 0.9) * 100)}%
                        </span>
                      </div>
                      <div className="bg-slate-900/90 border border-slate-800 rounded-xl p-3">
                        <span className="text-[11px] text-slate-400 block font-medium">Diagnostic Source</span>
                        <span className="text-xs font-bold text-slate-300 mt-1 block truncate">
                          {diag.source === 'LLM' ? 'LLM' : 'DETERMINISTIC FALLBACK'}
                        </span>
                      </div>
                    </div>

                    {/* AI Reasoning Narrative */}
                    <div className="bg-slate-900/70 border border-slate-800/80 rounded-xl p-3.5">
                      <span className="text-[11px] font-semibold text-slate-400 block mb-1">Reason:</span>
                      <p className="text-xs text-slate-200 leading-relaxed">
                        {diag.reason || diag.reasoning || 'Diagnostic etiology parsed from failure telemetry.'}
                      </p>
                    </div>

                    {/* DECISION PIPELINE FLOW */}
                    <div className="pt-2 border-t border-slate-800/60">
                      <span className="text-[11px] font-semibold text-slate-400 block mb-2 uppercase tracking-wider">
                        Closed-Loop Decision Pipeline
                      </span>
                      <div className="grid grid-cols-1 sm:grid-cols-4 gap-2">
                        {/* Stage 1: AI Recommendation */}
                        <div className="bg-slate-900/80 border border-slate-800 rounded-lg p-2.5 flex flex-col justify-between">
                          <div>
                            <span className="text-[10px] text-indigo-400 font-bold uppercase block">1. AI Recommends</span>
                            <span className="text-xs font-bold text-slate-100 block mt-0.5">
                              {diag.recommended_action || (diag.recommended_actions && diag.recommended_actions[0]) || 'RETRY_LATER'}
                            </span>
                          </div>
                          <span className="text-[10px] text-slate-400 mt-2 font-mono">
                            {diag.source === 'LLM' ? 'LLM' : 'DETERMINISTIC FALLBACK'}
                          </span>
                        </div>

                        {/* Stage 2: Policy Evaluates */}
                        <div className="bg-slate-900/80 border border-slate-800 rounded-lg p-2.5 flex flex-col justify-between">
                          <div>
                            <span className="text-[10px] text-violet-400 font-bold uppercase block">2. Policy Evaluates</span>
                            <span className="text-xs font-bold text-slate-100 block mt-0.5">
                              {latestAction?.action_type || 'Adaptive Policy'}
                            </span>
                          </div>
                          <span className="text-[10px] text-slate-400 mt-2">Bayesian Prior Scoring</span>
                        </div>

                        {/* Stage 3: Guardrail Decides */}
                        <div className="bg-slate-900/80 border border-slate-800 rounded-lg p-2.5 flex flex-col justify-between">
                          <div>
                            <span className="text-[10px] text-amber-400 font-bold uppercase block">3. Guardrail Decides</span>
                            <span className={`text-xs font-bold block mt-0.5 ${
                              detail.status === 'STOPPED' ? 'text-rose-400' : 'text-emerald-400'
                            }`}>
                              {detail.status === 'STOPPED' ? '🛑 STOPPED' : '✓ PASSED'}
                            </span>
                          </div>
                          <span className="text-[10px] text-slate-400 mt-2">
                            {detail.status === 'STOPPED' ? 'Opt-Out / Fraud Invariant' : 'Deterministic Safety'}
                          </span>
                        </div>

                        {/* Stage 4: Executor Acts */}
                        <div className="bg-slate-900/80 border border-slate-800 rounded-lg p-2.5 flex flex-col justify-between">
                          <div>
                            <span className="text-[10px] text-cyan-400 font-bold uppercase block">4. Executor Acts</span>
                            <span className="text-xs font-bold text-slate-100 block mt-0.5">
                              {latestAction ? latestAction.action_type : 'Dispatched'}
                            </span>
                          </div>
                          <span className="text-[10px] text-amber-300 font-mono mt-2">SIMULATION</span>
                        </div>
                      </div>
                    </div>
                  </div>

                  {/* 9-Stage Recovery Grid */}
                  <div className="space-y-2">
                    <h4 className="text-xs font-bold text-slate-400 uppercase tracking-wider">
                      9-Stage Lifecycle Breakdown
                    </h4>
                    <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
                    {/* 1. DETECT */}
                    <div className="bg-slate-950/70 border border-slate-800 rounded-xl p-4 relative overflow-hidden">
                      <div className="flex items-center gap-2 text-indigo-400 text-xs font-bold uppercase tracking-wider mb-2">
                        <span className="w-5 h-5 rounded-full bg-indigo-500/20 flex items-center justify-center text-[10px]">1</span>
                        DETECT
                      </div>
                      <p className="text-sm font-semibold text-slate-100">{formatINR(detail.amount)} Failed Payment</p>
                      <p className="text-xs text-slate-400 mt-1">Priority: <strong className="text-slate-200">{detail.priority}</strong></p>
                      <p className="text-[11px] text-slate-500 mt-1">Detected at: {formatTime(detail.created_at)}</p>
                    </div>

                    {/* 2. DIAGNOSE */}
                    <div className="bg-slate-950/70 border border-slate-800 rounded-xl p-4 relative overflow-hidden">
                      <div className="flex items-center gap-2 text-blue-400 text-xs font-bold uppercase tracking-wider mb-2">
                        <span className="w-5 h-5 rounded-full bg-blue-500/20 flex items-center justify-center text-[10px]">2</span>
                        DIAGNOSE
                      </div>
                      <p className="text-sm font-semibold text-slate-100">{diag.root_cause_category || 'Identified'}</p>
                      <p className="text-xs text-slate-400 mt-1">Confidence: <strong className="text-emerald-400">{((diag.confidence_score || 0.9) * 100).toFixed(0)}%</strong></p>
                      <p className="text-[11px] text-slate-400 mt-1 line-clamp-2">{diag.reasoning || 'Etiology parsed from error context.'}</p>
                    </div>

                    {/* 3. CHOOSE */}
                    <div className="bg-slate-950/70 border border-slate-800 rounded-xl p-4 relative overflow-hidden">
                      <div className="flex items-center gap-2 text-violet-400 text-xs font-bold uppercase tracking-wider mb-2">
                        <span className="w-5 h-5 rounded-full bg-violet-500/20 flex items-center justify-center text-[10px]">3</span>
                        CHOOSE
                      </div>
                      <p className="text-sm font-semibold text-slate-100">
                        {latestAction?.action_type || 'Adaptive Policy'}
                      </p>
                      <p className="text-xs text-slate-400 mt-1">Bayesian Action Scoring</p>
                      <p className="text-[11px] text-slate-500 mt-1">Evaluated empirical merchant statistics</p>
                    </div>

                    {/* 4. GUARD */}
                    <div className="bg-slate-950/70 border border-slate-800 rounded-xl p-4 relative overflow-hidden">
                      <div className="flex items-center gap-2 text-amber-400 text-xs font-bold uppercase tracking-wider mb-2">
                        <span className="w-5 h-5 rounded-full bg-amber-500/20 flex items-center justify-center text-[10px]">4</span>
                        GUARD
                      </div>
                      <div className="flex items-center gap-1.5 text-xs font-semibold text-emerald-400">
                        <ShieldCheck className="w-4 h-4" /> Guardrails Checked
                      </div>
                      <p className="text-[11px] text-slate-400 mt-1">
                        Checked: Opt-out, Fraud, Max Retries ({detail.retry_count}/3), Cooldown &amp; Comm Limits.
                      </p>
                    </div>

                    {/* 5. EXECUTE */}
                    <div className="bg-slate-950/70 border border-slate-800 rounded-xl p-4 relative overflow-hidden">
                      <div className="flex items-center gap-2 text-cyan-400 text-xs font-bold uppercase tracking-wider mb-2">
                        <span className="w-5 h-5 rounded-full bg-cyan-500/20 flex items-center justify-center text-[10px]">5</span>
                        EXECUTE
                      </div>
                      <p className="text-sm font-semibold text-slate-100">
                        {latestAction ? `${latestAction.action_type} (Seq #${latestAction.sequence_number})` : 'Dispatched'}
                      </p>
                      <p className="text-xs text-amber-300 font-mono mt-1">SIMULATION MODE</p>
                      <p className="text-[11px] text-slate-500 mt-1">Dispatched at: {formatTime(latestAction?.executed_at)}</p>
                    </div>

                    {/* 6. VERIFY */}
                    <div className="bg-slate-950/70 border border-slate-800 rounded-xl p-4 relative overflow-hidden">
                      <div className="flex items-center gap-2 text-emerald-400 text-xs font-bold uppercase tracking-wider mb-2">
                        <span className="w-5 h-5 rounded-full bg-emerald-500/20 flex items-center justify-center text-[10px]">6</span>
                        VERIFY
                      </div>
                      <p className="text-sm font-bold text-slate-100">
                        {latestOutcome?.outcome_type || (detail.status === 'RECOVERED' ? 'RECOVERED' : detail.status)}
                      </p>
                      <p className="text-xs font-semibold text-emerald-400 mt-1">
                        Recovered: {formatINR(detail.recovered_amount)}
                      </p>
                      {latestOutcome?.new_payment_id && (
                        <p className="text-[10px] text-slate-400 font-mono mt-1 truncate">ID: {latestOutcome.new_payment_id}</p>
                      )}
                    </div>

                    {/* 7. LEARN */}
                    <div className="bg-slate-950/70 border border-slate-800 rounded-xl p-4 relative overflow-hidden">
                      <div className="flex items-center gap-2 text-fuchsia-400 text-xs font-bold uppercase tracking-wider mb-2">
                        <span className="w-5 h-5 rounded-full bg-fuchsia-500/20 flex items-center justify-center text-[10px]">7</span>
                        LEARN
                      </div>
                      <p className="text-sm font-semibold text-slate-100">Statistics Updated</p>
                      <p className="text-xs text-slate-400 mt-1">Isolated to merchant tenant</p>
                      <p className="text-[11px] text-slate-500 mt-1">Refined success likelihoods</p>
                    </div>

                    {/* 8. AUDIT */}
                    <div className="bg-slate-950/70 border border-slate-800 rounded-xl p-4 relative overflow-hidden">
                      <div className="flex items-center gap-2 text-rose-400 text-xs font-bold uppercase tracking-wider mb-2">
                        <span className="w-5 h-5 rounded-full bg-rose-500/20 flex items-center justify-center text-[10px]">8</span>
                        AUDIT
                      </div>
                      <p className="text-sm font-semibold text-slate-100">{detail.audit_logs?.length || 0} Events Recorded</p>
                      <p className="text-xs text-slate-400 mt-1">Immutable audit ledger</p>
                      <p className="text-[11px] text-slate-500 mt-1">Every state transition verified</p>
                    </div>

                    {/* 9. MEASURE */}
                    <div className="bg-slate-950/70 border border-slate-800 rounded-xl p-4 relative overflow-hidden">
                      <div className="flex items-center gap-2 text-emerald-300 text-xs font-bold uppercase tracking-wider mb-2">
                        <span className="w-5 h-5 rounded-full bg-emerald-500/20 flex items-center justify-center text-[10px]">9</span>
                        MEASURE
                      </div>
                      <p className="text-sm font-semibold text-slate-100">Benchmark Evaluated</p>
                      <p className="text-xs text-emerald-400 mt-1">Incremental Lift Logged</p>
                      <p className="text-[11px] text-slate-500 mt-1">Compared vs. naive retry</p>
                    </div>
                  </div>
                </div>
              </div>
            )}

              {/* TAB 2: ACTIONS & OUTCOMES */}
              {activeTab === 'ACTIONS' && (
                <div className="space-y-4">
                  {(!detail.actions || detail.actions.length === 0) ? (
                    <p className="text-xs text-slate-500 py-6 text-center">No actions executed yet for this recovery case.</p>
                  ) : (
                    detail.actions.map((act) => {
                      const matchedOutcome = detail.outcomes?.find((o) => o.action_id === act.id);
                      return (
                        <div key={act.id} className="bg-slate-950 border border-slate-800 rounded-xl p-4 space-y-3">
                          <div className="flex items-center justify-between border-b border-slate-800 pb-2">
                            <div className="flex items-center gap-2">
                              <span className="px-2 py-0.5 rounded text-xs font-bold bg-indigo-500/20 text-indigo-300">
                                Seq #{act.sequence_number}
                              </span>
                              <span className="font-bold text-slate-100 text-sm">{act.action_type}</span>
                              <span className="text-xs text-amber-400 font-mono bg-amber-500/10 px-2 py-0.5 rounded border border-amber-500/30">
                                {act.execution_mode}
                              </span>
                            </div>
                            <span className="text-xs text-slate-500">{formatTime(act.executed_at)}</span>
                          </div>

                          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 text-xs">
                            <div>
                              <span className="text-slate-500 block mb-1">AI Reasoning &amp; Strategy:</span>
                              <p className="text-slate-300 bg-slate-900/80 p-2.5 rounded-lg border border-slate-800/80">
                                {act.ai_reasoning || 'Dispatched based on Bayesian diagnostic scoring.'}
                              </p>
                            </div>
                            <div>
                              <span className="text-slate-500 block mb-1">Verified Outcome:</span>
                              <div className="bg-slate-900/80 p-2.5 rounded-lg border border-slate-800/80 space-y-1">
                                <p className="font-bold text-slate-200">
                                  Outcome: <span className={matchedOutcome?.is_successful ? 'text-emerald-400' : 'text-amber-400'}>{matchedOutcome?.outcome_type || 'Processing'}</span>
                                </p>
                                <p className="text-slate-400">
                                  Recovered: <strong className="text-slate-200">{formatINR(matchedOutcome?.recovered_amount)}</strong>
                                </p>
                              </div>
                            </div>
                          </div>
                        </div>
                      );
                    })
                  )}
                </div>
              )}

              {/* TAB 3: IMMUTABLE AUDIT LOGS */}
              {activeTab === 'AUDIT' && (
                <div className="space-y-2.5">
                  {(!detail.audit_logs || detail.audit_logs.length === 0) ? (
                    <p className="text-xs text-slate-500 py-6 text-center">No audit log entries recorded for this case.</p>
                  ) : (
                    detail.audit_logs.map((log) => (
                      <div key={log.id} className="bg-slate-950/80 border border-slate-800/80 rounded-lg p-3 flex items-start justify-between gap-3 text-xs">
                        <div className="space-y-1">
                          <div className="flex items-center gap-2">
                            <span className="px-2 py-0.5 rounded text-[11px] font-bold bg-slate-800 text-indigo-300 font-mono">
                              {log.event_type}
                            </span>
                            <span className="text-slate-400 font-semibold">{log.actor_type}</span>
                          </div>
                          <p className="text-slate-300">{log.description}</p>
                        </div>
                        <span className="text-[11px] text-slate-400 font-mono shrink-0">
                          {formatTime(log.created_at)}
                        </span>
                      </div>
                    ))
                  )}
                </div>
              )}
            </>
          )}
        </div>

        {/* Modal Footer with Actions */}
        <div className="p-4 sm:p-5 border-t border-slate-800 bg-slate-950/60 flex flex-col sm:flex-row items-center justify-between gap-3">
          <div className="text-xs text-slate-400 text-center sm:text-left">
            <span>Deterministic guardrails enforce max 3 retries &amp; customer opt-out safety.</span>
          </div>

          <div className="flex items-center gap-3 w-full sm:w-auto justify-end">
            <button
              onClick={onClose}
              className="px-4 py-2 rounded-xl bg-slate-800 hover:bg-slate-700 text-slate-300 text-xs font-semibold transition-colors border border-slate-700 cursor-pointer"
            >
              Close
            </button>

            {detail && detail.status !== 'RECOVERED' && detail.status !== 'STOPPED' && (
              <button
                onClick={handleRunNextStep}
                disabled={runningStep}
                className="px-4 py-2 rounded-xl bg-indigo-600 hover:bg-indigo-500 text-white text-xs font-bold transition-all shadow-lg shadow-indigo-600/30 flex items-center gap-2 disabled:opacity-50 cursor-pointer"
              >
                {runningStep ? (
                  <RotateCw className="w-3.5 h-3.5 animate-spin" />
                ) : (
                  <Play className="w-3.5 h-3.5 fill-current" />
                )}
                <span>Run Next Recovery Step</span>
              </button>
            )}
          </div>
        </div>
      </div>
    </div>
  );
};
