import React, { useState } from 'react';
import {
  Search,
  Filter,
  Eye,
  Play,
  RotateCw,
  AlertCircle,
  CheckCircle2,
  Clock,
  Ban,
  ArrowUpRight,
  ShieldAlert,
} from 'lucide-react';
import { RecoveryCase, CaseStatus, RootCauseCategory } from '../../types';

interface RecoveryCasesTableProps {
  cases: RecoveryCase[];
  loading: boolean;
  onSelectCase: (caseId: string) => void;
  onRunCaseStep: (caseId: string) => void;
  runningCaseId: string | null;
}

export const RecoveryCasesTable: React.FC<RecoveryCasesTableProps> = ({
  cases,
  loading,
  onSelectCase,
  onRunCaseStep,
  runningCaseId,
}) => {
  const [searchTerm, setSearchTerm] = useState('');
  const [statusFilter, setStatusFilter] = useState<string>('ALL');

  const formatINR = (val: number) => {
    return new Intl.NumberFormat('en-IN', {
      style: 'currency',
      currency: 'INR',
      maximumFractionDigits: 2,
    }).format(val);
  };

  const getStatusBadge = (status: CaseStatus) => {
    switch (status) {
      case 'RECOVERED':
        return (
          <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-xs font-semibold bg-emerald-500/10 text-emerald-400 border border-emerald-500/30">
            <CheckCircle2 className="w-3 h-3" /> Recovered
          </span>
        );
      case 'WAITING':
        return (
          <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-xs font-semibold bg-amber-500/10 text-amber-400 border border-amber-500/30">
            <Clock className="w-3 h-3" /> Waiting / Retryable
          </span>
        );
      case 'ESCALATED':
        return (
          <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-xs font-semibold bg-purple-500/10 text-purple-300 border border-purple-500/30">
            <ArrowUpRight className="w-3 h-3" /> Escalated (VIP)
          </span>
        );
      case 'STOPPED':
        return (
          <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-xs font-semibold bg-slate-700/50 text-slate-400 border border-slate-600">
            <Ban className="w-3 h-3" /> Stopped (Guardrail)
          </span>
        );
      case 'FAILED':
        return (
          <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-xs font-semibold bg-rose-500/10 text-rose-400 border border-rose-500/30">
            <AlertCircle className="w-3 h-3" /> Failed
          </span>
        );
      case 'EXECUTING':
        return (
          <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-xs font-semibold bg-cyan-500/10 text-cyan-300 border border-cyan-500/30 animate-pulse">
            <RotateCw className="w-3 h-3 animate-spin" /> Executing
          </span>
        );
      case 'APPROVED':
        return (
          <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-xs font-semibold bg-blue-500/10 text-blue-300 border border-blue-500/30">
            Approved
          </span>
        );
      case 'DIAGNOSED':
        return (
          <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-xs font-semibold bg-indigo-500/10 text-indigo-300 border border-indigo-500/30">
            Diagnosed
          </span>
        );
      default:
        return (
          <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-xs font-semibold bg-slate-800 text-slate-300 border border-slate-700">
            {status}
          </span>
        );
    }
  };

  const getPriorityBadge = (priority: string) => {
    switch (priority) {
      case 'CRITICAL':
        return (
          <span className="inline-flex items-center px-2 py-0.5 rounded text-[11px] font-bold bg-rose-950/80 text-rose-300 border border-rose-800">
            CRITICAL
          </span>
        );
      case 'HIGH':
        return (
          <span className="inline-flex items-center px-2 py-0.5 rounded text-[11px] font-bold bg-amber-950/80 text-amber-300 border border-amber-800">
            HIGH
          </span>
        );
      case 'MEDIUM':
        return (
          <span className="inline-flex items-center px-2 py-0.5 rounded text-[11px] font-semibold bg-indigo-950/80 text-indigo-300 border border-indigo-800">
            MEDIUM
          </span>
        );
      default:
        return (
          <span className="inline-flex items-center px-2 py-0.5 rounded text-[11px] font-medium bg-slate-800 text-slate-400 border border-slate-700">
            LOW
          </span>
        );
    }
  };

  const getCauseBadge = (cause?: RootCauseCategory | string) => {
    switch (cause) {
      case 'NETWORK_TIMEOUT':
        return (
          <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-xs font-medium bg-blue-950/60 text-blue-300 border border-blue-800/60">
            Network Timeout
          </span>
        );
      case 'GATEWAY_ERROR':
        return (
          <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-xs font-medium bg-amber-950/60 text-amber-300 border border-amber-800/60">
            Gateway / Bank Down
          </span>
        );
      case 'INSUFFICIENT_FUNDS':
        return (
          <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-xs font-medium bg-cyan-950/60 text-cyan-300 border border-cyan-800/60">
            Low Funds
          </span>
        );
      case 'USER_DROPPED':
        return (
          <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-xs font-medium bg-indigo-950/60 text-indigo-300 border border-indigo-800/60">
            User Dropped / Expired
          </span>
        );
      case 'CARD_LIMIT_EXCEEDED':
        return (
          <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-xs font-medium bg-violet-950/60 text-violet-300 border border-violet-800/60">
            Card Limit Exceeded
          </span>
        );
      case 'FRAUD_DECLINE':
        return (
          <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-xs font-medium bg-rose-950/80 text-rose-300 border border-rose-800">
            <ShieldAlert className="w-3 h-3" /> Fraud Decline
          </span>
        );
      default:
        return (
          <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-slate-800 text-slate-400 border border-slate-700">
            {cause || 'Processing'}
          </span>
        );
    }
  };

  const filteredCases = cases.filter((c) => {
    const matchesSearch =
      (c.customer_name || '').toLowerCase().includes(searchTerm.toLowerCase()) ||
      (c.customer_email || '').toLowerCase().includes(searchTerm.toLowerCase()) ||
      c.id.toLowerCase().includes(searchTerm.toLowerCase()) ||
      c.payment_id.toLowerCase().includes(searchTerm.toLowerCase()) ||
      (c.diagnosis_summary?.root_cause_category || '').toLowerCase().includes(searchTerm.toLowerCase());

    const matchesStatus = statusFilter === 'ALL' || c.status === statusFilter;

    return matchesSearch && matchesStatus;
  });

  return (
    <div className="bg-slate-900 border border-slate-800 rounded-2xl overflow-hidden shadow-xl">
      {/* Table Header & Controls */}
      <div className="p-4 sm:p-6 border-b border-slate-800 flex flex-col md:flex-row md:items-center md:justify-between gap-4">
        <div>
          <h2 className="text-xl font-bold text-slate-100">Recovery Cases</h2>
          <p className="text-xs sm:text-sm text-slate-400 mt-0.5">
            Active and resolved recovery lifecycles with diagnosis etiology and verifiable outcomes.
          </p>
        </div>

        <div className="flex flex-wrap items-center gap-2.5">
          {/* Search */}
          <div className="relative min-w-[200px] sm:min-w-[240px]">
            <Search className="w-4 h-4 text-slate-400 absolute left-3 top-1/2 -translate-y-1/2 pointer-events-none" />
            <input
              type="text"
              placeholder="Search customer, case, error..."
              value={searchTerm}
              onChange={(e) => setSearchTerm(e.target.value)}
              className="w-full bg-slate-950 border border-slate-800 rounded-xl pl-9 pr-3.5 py-2 text-xs sm:text-sm text-slate-200 placeholder-slate-500 focus:outline-none focus:border-indigo-500 transition-colors"
            />
          </div>

          {/* Status Filter */}
          <div className="flex items-center gap-1.5 bg-slate-950 border border-slate-800 rounded-xl px-2.5 py-1.5">
            <Filter className="w-3.5 h-3.5 text-slate-400" />
            <select
              value={statusFilter}
              onChange={(e) => setStatusFilter(e.target.value)}
              className="bg-transparent text-xs text-slate-300 font-medium focus:outline-none cursor-pointer pr-1"
            >
              <option value="ALL">All Statuses</option>
              <option value="RECOVERED">Recovered</option>
              <option value="WAITING">Waiting</option>
              <option value="ESCALATED">Escalated</option>
              <option value="STOPPED">Stopped</option>
              <option value="FAILED">Failed</option>
            </select>
          </div>
        </div>
      </div>

      {/* Table Content */}
      <div className="overflow-x-auto">
        <table className="w-full text-left text-xs sm:text-sm border-collapse">
          <thead>
            <tr className="bg-slate-950/60 border-b border-slate-800 text-slate-400 text-[11px] font-semibold uppercase tracking-wider">
              <th className="py-3 px-4">Customer &amp; Payment</th>
              <th className="py-3 px-4">Amount</th>
              <th className="py-3 px-4">Diagnosis &amp; Root Cause</th>
              <th className="py-3 px-4">Priority</th>
              <th className="py-3 px-4">Status</th>
              <th className="py-3 px-4 text-center">Retries / Comms</th>
              <th className="py-3 px-4">Recovered Amt</th>
              <th className="py-3 px-4 text-right">Actions</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-800/70">
            {loading ? (
              [...Array(5)].map((_, i) => (
                <tr key={i} className="animate-pulse">
                  <td className="py-4 px-4"><div className="w-32 h-4 bg-slate-800 rounded mb-1" /><div className="w-24 h-3 bg-slate-800/60 rounded" /></td>
                  <td className="py-4 px-4"><div className="w-16 h-4 bg-slate-800 rounded" /></td>
                  <td className="py-4 px-4"><div className="w-28 h-4 bg-slate-800 rounded" /></td>
                  <td className="py-4 px-4"><div className="w-14 h-4 bg-slate-800 rounded" /></td>
                  <td className="py-4 px-4"><div className="w-20 h-4 bg-slate-800 rounded" /></td>
                  <td className="py-4 px-4 text-center"><div className="w-8 h-4 bg-slate-800 rounded mx-auto" /></td>
                  <td className="py-4 px-4"><div className="w-16 h-4 bg-slate-800 rounded" /></td>
                  <td className="py-4 px-4 text-right"><div className="w-16 h-6 bg-slate-800 rounded ml-auto" /></td>
                </tr>
              ))
            ) : filteredCases.length === 0 ? (
              <tr>
                <td colSpan={8} className="py-12 text-center text-slate-400">
                  <div className="max-w-md mx-auto space-y-2">
                    <AlertCircle className="w-8 h-8 text-slate-500 mx-auto" />
                    <p className="font-semibold text-slate-300">No recovery cases found</p>
                    <p className="text-xs text-slate-500">
                      Click <strong className="text-indigo-400">"Run Demo Recovery"</strong> above to ingest realistic test payment failures and start the automated engine.
                    </p>
                  </div>
                </td>
              </tr>
            ) : (
              filteredCases.map((c) => {
                const isRunning = runningCaseId === c.id;
                return (
                  <tr
                    key={c.id}
                    className="hover:bg-slate-800/40 transition-colors group cursor-pointer"
                    onClick={() => onSelectCase(c.id)}
                  >
                    {/* Customer */}
                    <td className="py-3.5 px-4">
                      <div className="font-semibold text-slate-100 group-hover:text-indigo-300 transition-colors">
                        {c.customer_name || 'Anonymous Customer'}
                      </div>
                      <div className="text-[11px] text-slate-400 truncate max-w-[200px]">
                        {c.customer_email || c.payment_id}
                      </div>
                    </td>

                    {/* Amount */}
                    <td className="py-3.5 px-4 font-semibold text-slate-200 whitespace-nowrap">
                      {formatINR(c.amount)}
                    </td>

                    {/* Diagnosis */}
                    <td className="py-3.5 px-4">
                      <div className="flex flex-col items-start gap-1">
                        {getCauseBadge(c.diagnosis_summary?.root_cause_category)}
                        {c.diagnosis_summary?.confidence_score && (
                          <span className="text-[10px] text-slate-400">
                            Confidence: {(c.diagnosis_summary.confidence_score * 100).toFixed(0)}%
                          </span>
                        )}
                      </div>
                    </td>

                    {/* Priority */}
                    <td className="py-3.5 px-4">
                      {getPriorityBadge(c.priority)}
                    </td>

                    {/* Status */}
                    <td className="py-3.5 px-4 whitespace-nowrap">
                      {getStatusBadge(c.status)}
                    </td>

                    {/* Retry / Comms */}
                    <td className="py-3.5 px-4 text-center whitespace-nowrap text-slate-300 font-mono text-xs">
                      <span title="Retries">{c.retry_count}</span>
                      <span className="text-slate-600 mx-1">/</span>
                      <span title="Customer Communications">{c.communication_count}</span>
                    </td>

                    {/* Recovered Amount */}
                    <td className="py-3.5 px-4 whitespace-nowrap font-bold text-emerald-400">
                      {c.recovered_amount > 0 ? formatINR(c.recovered_amount) : <span className="text-slate-600 font-normal">₹0.00</span>}
                    </td>

                    {/* Actions */}
                    <td className="py-3.5 px-4 text-right whitespace-nowrap" onClick={(e) => e.stopPropagation()}>
                      <div className="flex items-center justify-end gap-1.5">
                        {/* Run Next Step */}
                        {c.status !== 'RECOVERED' && c.status !== 'STOPPED' && (
                          <button
                            onClick={() => onRunCaseStep(c.id)}
                            disabled={isRunning}
                            className="inline-flex items-center gap-1 px-2.5 py-1 rounded-lg bg-indigo-600/20 hover:bg-indigo-600/30 text-indigo-300 hover:text-indigo-200 border border-indigo-500/30 text-xs font-semibold transition-all disabled:opacity-50 cursor-pointer"
                            title="Execute next permitted recovery cycle step"
                          >
                            {isRunning ? (
                              <RotateCw className="w-3.5 h-3.5 animate-spin" />
                            ) : (
                              <Play className="w-3.5 h-3.5 fill-current" />
                            )}
                            <span>Run Step</span>
                          </button>
                        )}

                        {/* View Details */}
                        <button
                          onClick={() => onSelectCase(c.id)}
                          className="inline-flex items-center gap-1 px-2 py-1 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-300 text-xs transition-colors border border-slate-700 cursor-pointer"
                          title="View 9-Stage Recovery Timeline & Audit Trail"
                        >
                          <Eye className="w-3.5 h-3.5" />
                          <span>Timeline</span>
                        </button>
                      </div>
                    </td>
                  </tr>
                );
              })
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
};
