import React, { useState } from 'react';
import { ShieldCheck, Mail, ArrowRight, AlertCircle, CheckCircle2 } from 'lucide-react';
import { useAuth } from '../auth/AuthContext';
import { isSupabaseConfigured } from '../auth/supabaseClient';

export const LoginPage: React.FC = () => {
  const [email, setEmail] = useState('');
  const [submitted, setSubmitted] = useState(false);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const { signInWithEmail } = useAuth();

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!email) return;

    setErrorMsg(null);
    if (!isSupabaseConfigured) {
      setErrorMsg("Supabase Auth is in foundation setup mode. Configure SUPABASE_URL and SUPABASE_ANON_KEY to enable live authentication.");
      return;
    }

    const { error } = await signInWithEmail(email);
    if (error) {
      setErrorMsg(error.message);
    } else {
      setSubmitted(true);
    }
  };

  return (
    <div className="max-w-md mx-auto my-12 bg-slate-900 border border-slate-800 rounded-xl p-8 shadow-xl">
      <div className="text-center mb-8">
        <div className="w-12 h-12 rounded-xl bg-indigo-600/20 text-indigo-400 border border-indigo-500/30 flex items-center justify-center mx-auto mb-4">
          <ShieldCheck className="w-6 h-6" />
        </div>
        <h1 className="text-2xl font-bold text-slate-100 tracking-tight">Merchant Access</h1>
        <p className="text-sm text-slate-400 mt-1.5">Sign in to manage payment recovery policies and audit logs.</p>
      </div>

      {!isSupabaseConfigured && (
        <div className="mb-6 p-4 rounded-lg bg-amber-950/30 border border-amber-800/40 text-amber-300 text-xs flex items-start gap-2.5">
          <AlertCircle className="w-4 h-4 shrink-0 mt-0.5" />
          <div>
            <p className="font-semibold mb-1">Foundation Mode Active</p>
            <p className="text-amber-300/80 leading-relaxed">
              Supabase Auth client is initialized in placeholder mode. Real authentication will be activated during the database & auth configuration step.
            </p>
          </div>
        </div>
      )}

      {submitted ? (
        <div className="p-4 rounded-lg bg-emerald-950/30 border border-emerald-800/40 text-emerald-300 text-sm flex items-start gap-2.5">
          <CheckCircle2 className="w-5 h-5 shrink-0 mt-0.5" />
          <div>
            <p className="font-semibold">Check your email</p>
            <p className="text-xs text-emerald-300/80 mt-1">A magic link has been sent to {email}.</p>
          </div>
        </div>
      ) : (
        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="block text-xs font-medium text-slate-300 mb-1.5 uppercase tracking-wider">
              Merchant Work Email
            </label>
            <div className="relative">
              <Mail className="w-4 h-4 text-slate-500 absolute left-3.5 top-1/2 -translate-y-1/2" />
              <input
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="merchant@company.com"
                required
                className="w-full bg-slate-950 border border-slate-800 rounded-lg pl-10 pr-4 py-2.5 text-sm text-slate-100 placeholder-slate-600 focus:outline-none focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500 transition-colors"
              />
            </div>
          </div>

          {errorMsg && (
            <p className="text-xs text-rose-400 bg-rose-950/30 border border-rose-800/40 p-2.5 rounded-md">
              {errorMsg}
            </p>
          )}

          <button
            type="submit"
            className="w-full flex items-center justify-center gap-2 bg-indigo-600 hover:bg-indigo-500 text-white font-medium py-2.5 rounded-lg text-sm transition-colors shadow-lg shadow-indigo-600/20 cursor-pointer"
          >
            <span>Continue with Email</span>
            <ArrowRight className="w-4 h-4" />
          </button>
        </form>
      )}
    </div>
  );
};
