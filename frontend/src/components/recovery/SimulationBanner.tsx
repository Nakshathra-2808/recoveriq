import React from 'react';
import { Sparkles, ShieldCheck, CreditCard, Cpu } from 'lucide-react';

interface SimulationBannerProps {
  mode?: 'SIMULATION' | 'RAZORPAY_TEST' | 'DRY_RUN';
}

export const SimulationBanner: React.FC<SimulationBannerProps> = ({ mode = 'SIMULATION' }) => {
  if (mode === 'RAZORPAY_TEST') {
    return (
      <div className="bg-gradient-to-r from-blue-500/10 via-blue-500/5 to-transparent border border-blue-500/30 rounded-xl p-3.5 sm:p-4 text-blue-200 text-xs sm:text-sm flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3 shadow-inner">
        <div className="flex items-center gap-2.5">
          <div className="w-7 h-7 rounded-lg bg-blue-500/20 text-blue-400 flex items-center justify-center shrink-0 border border-blue-500/40 font-bold">
            <CreditCard className="w-4 h-4" />
          </div>
          <div>
            <span className="font-bold text-blue-300 uppercase tracking-wider text-xs block sm:inline mr-2">
              Execution Mode: RAZORPAY TEST MODE
            </span>
            <span className="text-blue-200/90 text-xs">
              Razorpay Test Environment — No real money movement. Interacts securely with Razorpay's sandbox APIs using test credentials.
            </span>
          </div>
        </div>
        <div className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md bg-blue-500/20 border border-blue-500/40 text-blue-300 text-xs font-semibold shrink-0">
          <ShieldCheck className="w-3.5 h-3.5" />
          Razorpay Sandbox
        </div>
      </div>
    );
  }

  if (mode === 'DRY_RUN') {
    return (
      <div className="bg-gradient-to-r from-slate-500/10 via-slate-500/5 to-transparent border border-slate-700 rounded-xl p-3.5 sm:p-4 text-slate-300 text-xs sm:text-sm flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3 shadow-inner">
        <div className="flex items-center gap-2.5">
          <div className="w-7 h-7 rounded-lg bg-slate-800 text-slate-400 flex items-center justify-center shrink-0 border border-slate-700 font-bold">
            <Cpu className="w-4 h-4" />
          </div>
          <div>
            <span className="font-bold text-slate-200 uppercase tracking-wider text-xs block sm:inline mr-2">
              Execution Mode: DRY RUN
            </span>
            <span className="text-slate-400 text-xs">
              Evaluates all Bayesian policies and deterministic safety guardrails without dispatching external network calls.
            </span>
          </div>
        </div>
        <div className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md bg-slate-800 border border-slate-700 text-slate-300 text-xs font-semibold shrink-0">
          <ShieldCheck className="w-3.5 h-3.5" />
          Dry Run Engine
        </div>
      </div>
    );
  }

  return (
    <div className="bg-gradient-to-r from-amber-500/10 via-amber-500/5 to-transparent border border-amber-500/30 rounded-xl p-3.5 sm:p-4 text-amber-200 text-xs sm:text-sm flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3 shadow-inner">
      <div className="flex items-center gap-2.5">
        <div className="w-7 h-7 rounded-lg bg-amber-500/20 text-amber-400 flex items-center justify-center shrink-0 border border-amber-500/40 font-bold">
          <Sparkles className="w-4 h-4" />
        </div>
        <div>
          <span className="font-bold text-amber-300 uppercase tracking-wider text-xs block sm:inline mr-2">
            Execution Mode: SIMULATION MODE
          </span>
          <span className="text-amber-200/90 text-xs">
            Payment recoveries, gateway retries, and customer notifications execute within a high-fidelity, reproducible sandbox. No live card charges or actual money movement occur in this mode.
          </span>
        </div>
      </div>
      <div className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md bg-amber-500/20 border border-amber-500/40 text-amber-300 text-xs font-semibold shrink-0">
        <ShieldCheck className="w-3.5 h-3.5" />
        Safe Test Harness
      </div>
    </div>
  );
};

