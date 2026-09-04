import React from 'react';
import { TrendingUp, AlertTriangle, ShieldCheck, Zap, Percent, ArrowUpRight, Scale } from 'lucide-react';
import { RecoveryMetrics } from '../../types';

interface MetricsCardsProps {
  metrics: RecoveryMetrics | null;
  loading: boolean;
}

export const MetricsCards: React.FC<MetricsCardsProps> = ({ metrics, loading }) => {
  const formatINR = (val: number | undefined) => {
    if (val === undefined || val === null) return '₹0.00';
    return new Intl.NumberFormat('en-IN', {
      style: 'currency',
      currency: 'INR',
      maximumFractionDigits: 2,
    }).format(val);
  };

  const formatPct = (val: number | undefined) => {
    if (val === undefined || val === null) return '0.0%';
    return `${val.toFixed(1)}%`;
  };

  if (loading) {
    return (
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-6 gap-4">
        {[...Array(6)].map((_, i) => (
          <div key={i} className="bg-slate-900 border border-slate-800 rounded-xl p-4 animate-pulse">
            <div className="w-24 h-3 bg-slate-800 rounded mb-3" />
            <div className="w-32 h-6 bg-slate-800 rounded mb-2" />
            <div className="w-20 h-2 bg-slate-800 rounded" />
          </div>
        ))}
      </div>
    );
  }

  const successRatePct = (metrics?.overall_recovery_rate || 0) * 100;
  const liftPct = metrics?.recovery_lift_percentage || 0;
  const incrementalRev = metrics?.incremental_revenue_recovered || 0;

  return (
    <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-6 gap-4">
      {/* 1. Revenue at Risk */}
      <div className="bg-slate-900/90 border border-slate-800 hover:border-slate-700 transition-all rounded-xl p-4 shadow-sm relative overflow-hidden group">
        <div className="flex items-center justify-between text-slate-400 mb-2">
          <span className="text-xs font-semibold uppercase tracking-wider">Revenue at Risk</span>
          <div className="w-7 h-7 rounded-lg bg-rose-500/10 text-rose-400 border border-rose-500/20 flex items-center justify-center">
            <AlertTriangle className="w-4 h-4" />
          </div>
        </div>
        <div className="text-xl sm:text-2xl font-bold text-slate-100 tracking-tight">
          {formatINR(metrics?.total_revenue_at_risk)}
        </div>
        <p className="text-[11px] text-slate-400 mt-1 flex items-center gap-1">
          <span>Total failed transaction value</span>
        </p>
      </div>

      {/* 2. RecoverIQ Recovered */}
      <div className="bg-gradient-to-br from-slate-900 via-slate-900 to-emerald-950/30 border border-emerald-500/30 hover:border-emerald-500/50 transition-all rounded-xl p-4 shadow-sm relative overflow-hidden group">
        <div className="flex items-center justify-between text-emerald-400 mb-2">
          <span className="text-xs font-semibold uppercase tracking-wider">RecoverIQ Recovered</span>
          <div className="w-7 h-7 rounded-lg bg-emerald-500/20 text-emerald-300 border border-emerald-500/30 flex items-center justify-center">
            <ShieldCheck className="w-4 h-4" />
          </div>
        </div>
        <div className="text-xl sm:text-2xl font-bold text-emerald-300 tracking-tight">
          {formatINR(metrics?.recoveriq_recovered_revenue)}
        </div>
        <p className="text-[11px] text-emerald-400/80 mt-1 flex items-center gap-1">
          <span>{metrics?.total_cases_recovered || 0} of {metrics?.total_cases_processed || 0} cases recovered</span>
        </p>
      </div>

      {/* 3. Baseline Recovered */}
      <div className="bg-slate-900/90 border border-slate-800 hover:border-slate-700 transition-all rounded-xl p-4 shadow-sm relative overflow-hidden group">
        <div className="flex items-center justify-between text-slate-400 mb-2">
          <span className="text-xs font-semibold uppercase tracking-wider">Baseline Recovered</span>
          <div className="w-7 h-7 rounded-lg bg-slate-800 text-slate-400 border border-slate-700 flex items-center justify-center">
            <Scale className="w-4 h-4" />
          </div>
        </div>
        <div className="text-xl sm:text-2xl font-bold text-slate-300 tracking-tight">
          {formatINR(metrics?.baseline_recovered_revenue)}
        </div>
        <p className="text-[11px] text-slate-400 mt-1">
          <span>Fixed naive retry standard</span>
        </p>
      </div>

      {/* 4. Incremental Revenue */}
      <div className="bg-gradient-to-br from-slate-900 via-indigo-950/20 to-indigo-950/40 border border-indigo-500/30 hover:border-indigo-500/50 transition-all rounded-xl p-4 shadow-sm relative overflow-hidden group">
        <div className="flex items-center justify-between text-indigo-400 mb-2">
          <span className="text-xs font-semibold uppercase tracking-wider">Incremental Revenue</span>
          <div className="w-7 h-7 rounded-lg bg-indigo-500/20 text-indigo-300 border border-indigo-500/30 flex items-center justify-center">
            <Zap className="w-4 h-4" />
          </div>
        </div>
        <div className="text-xl sm:text-2xl font-bold text-indigo-200 tracking-tight">
          {formatINR(incrementalRev)}
        </div>
        <p className="text-[11px] text-indigo-300/80 mt-1 flex items-center gap-1">
          <span>Net gain above baseline</span>
        </p>
      </div>

      {/* 5. Recovery Lift */}
      <div className="bg-slate-900/90 border border-cyan-500/20 hover:border-cyan-500/40 transition-all rounded-xl p-4 shadow-sm relative overflow-hidden group">
        <div className="flex items-center justify-between text-cyan-400 mb-2">
          <span className="text-xs font-semibold uppercase tracking-wider">Recovery Lift</span>
          <div className="w-7 h-7 rounded-lg bg-cyan-500/10 text-cyan-300 border border-cyan-500/20 flex items-center justify-center">
            <TrendingUp className="w-4 h-4" />
          </div>
        </div>
        <div className="text-xl sm:text-2xl font-bold text-cyan-300 tracking-tight flex items-baseline gap-1">
          {formatPct(liftPct)}
          {liftPct > 0 && <ArrowUpRight className="w-4 h-4 text-cyan-400 inline" />}
        </div>
        <p className="text-[11px] text-cyan-400/80 mt-1">
          <span>Vs. standard retry strategy</span>
        </p>
      </div>

      {/* 6. Recovery Success Rate */}
      <div className="bg-slate-900/90 border border-slate-800 hover:border-slate-700 transition-all rounded-xl p-4 shadow-sm relative overflow-hidden group">
        <div className="flex items-center justify-between text-slate-400 mb-2">
          <span className="text-xs font-semibold uppercase tracking-wider">Success Rate</span>
          <div className="w-7 h-7 rounded-lg bg-violet-500/10 text-violet-300 border border-violet-500/20 flex items-center justify-center">
            <Percent className="w-4 h-4" />
          </div>
        </div>
        <div className="text-xl sm:text-2xl font-bold text-slate-100 tracking-tight">
          {formatPct(successRatePct)}
        </div>
        <p className="text-[11px] text-slate-400 mt-1">
          <span>{metrics?.total_cases_recovered || 0} / {metrics?.total_cases_processed || 0} cases resolved</span>
        </p>
      </div>
    </div>
  );
};
