import React, { useEffect, useState } from 'react';
import { Activity, Server, AlertCircle, CheckCircle2, Shield } from 'lucide-react';
import { fetchHealth } from '../services/api';
import { HealthStatus } from '../types';

export const DashboardPage: React.FC = () => {
  const [health, setHealth] = useState<HealthStatus | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetchHealth()
      .then((data) => {
        setHealth(data);
        setLoading(false);
      })
      .catch((err) => {
        setError(err.message);
        setLoading(false);
      });
  }, []);

  return (
    <div className="space-y-8">
      {/* Header Banner */}
      <div className="bg-slate-900 border border-slate-800 rounded-2xl p-6 sm:p-8">
        <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-4">
          <div>
            <div className="inline-flex items-center gap-2 px-2.5 py-1 rounded-full bg-indigo-950/80 border border-indigo-800/50 text-indigo-300 text-xs font-semibold uppercase tracking-wider mb-3">
              <span className="w-2 h-2 rounded-full bg-indigo-400 animate-pulse" />
              Phase 1: Project Foundation
            </div>
            <h1 className="text-3xl font-bold text-slate-100 tracking-tight">RecoverIQ Recovery Console</h1>
            <p className="text-slate-400 text-sm mt-1 max-w-2xl">
              Adaptive AI revenue recovery engine. Diagnoses failure patterns, determines optimal recovery actions, and operates under deterministic server-side guardrails.
            </p>
          </div>

          <div className="flex items-center gap-3">
            <div className="bg-slate-950 border border-slate-800 rounded-xl px-4 py-3 text-right">
              <span className="text-xs text-slate-500 block uppercase font-medium">Backend Status</span>
              {loading ? (
                <span className="text-sm font-semibold text-slate-400">Connecting...</span>
              ) : health ? (
                <span className="text-sm font-semibold text-emerald-400 flex items-center gap-1.5 justify-end">
                  <CheckCircle2 className="w-4 h-4" /> Healthy ({health.version})
                </span>
              ) : (
                <span className="text-sm font-semibold text-rose-400 flex items-center gap-1.5 justify-end">
                  <AlertCircle className="w-4 h-4" /> Offline
                </span>
              )}
            </div>
          </div>
        </div>
      </div>

      {/* System Status Grid */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
        <div className="bg-slate-900/60 border border-slate-800/80 rounded-xl p-5">
          <div className="flex items-center justify-between mb-3">
            <span className="text-xs font-semibold uppercase tracking-wider text-slate-400">Backend API</span>
            <Server className="w-4 h-4 text-indigo-400" />
          </div>
          <div className="text-xl font-bold text-slate-100">
            {health?.service || 'FastAPI Core'}
          </div>
          <p className="text-xs text-slate-500 mt-1">
            Status: {health?.status === 'ok' ? 'Online & Responsive' : 'Waiting for connection'}
          </p>
        </div>

        <div className="bg-slate-900/60 border border-slate-800/80 rounded-xl p-5">
          <div className="flex items-center justify-between mb-3">
            <span className="text-xs font-semibold uppercase tracking-wider text-slate-400">Decision Engine</span>
            <Activity className="w-4 h-4 text-amber-400" />
          </div>
          <div className="text-xl font-bold text-slate-100">Adaptive Policy Engine</div>
          <p className="text-xs text-slate-500 mt-1">Foundation ready (Policy logic uninitialized)</p>
        </div>

        <div className="bg-slate-900/60 border border-slate-800/80 rounded-xl p-5">
          <div className="flex items-center justify-between mb-3">
            <span className="text-xs font-semibold uppercase tracking-wider text-slate-400">Safety System</span>
            <Shield className="w-4 h-4 text-emerald-400" />
          </div>
          <div className="text-xl font-bold text-slate-100">Deterministic Guardrails</div>
          <p className="text-xs text-slate-500 mt-1">Server-side execution limits ready</p>
        </div>
      </div>

      {/* Notice Section */}
      <div className="bg-slate-900/40 border border-slate-800 rounded-xl p-6">
        <h2 className="text-base font-semibold text-slate-200 mb-2">Foundation Stage Complete</h2>
        <p className="text-sm text-slate-400 leading-relaxed max-w-3xl">
          The modular monolith architecture is structured with FastAPI backend, React + TypeScript frontend, Supabase migration templates, deterministic guardrails scaffolds, and baseline vs. RecoverIQ metrics definitions.
        </p>
        {error && (
          <div className="mt-4 p-3 rounded-lg bg-rose-950/40 border border-rose-800/50 text-rose-300 text-xs">
            Backend connection error: {error}. Ensure the FastAPI server is running at <code className="bg-rose-900/50 px-1 py-0.5 rounded">http://localhost:8000</code>.
          </div>
        )}
      </div>
    </div>
  );
};
