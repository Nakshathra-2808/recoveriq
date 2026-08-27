import React from 'react';
import { Link, useLocation } from 'react-router-dom';
import { ShieldCheck, LogIn, LayoutDashboard } from 'lucide-react';
import { useAuth } from '../auth/AuthContext';

export const Navbar: React.FC = () => {
  const { isAuthenticated, signOut } = useAuth();
  const location = useLocation();

  return (
    <header className="border-b border-slate-800 bg-slate-900/80 backdrop-blur sticky top-0 z-50">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 h-16 flex items-center justify-between">
        <Link to="/" className="flex items-center space-x-2.5">
          <div className="w-8 h-8 rounded-lg bg-indigo-600 flex items-center justify-center text-white shadow-md shadow-indigo-500/20">
            <ShieldCheck className="w-5 h-5" />
          </div>
          <div className="flex flex-col">
            <span className="font-bold text-lg text-slate-100 tracking-tight flex items-center gap-1.5">
              Recover<span className="text-indigo-400">IQ</span>
              <span className="text-xs font-semibold uppercase tracking-wider px-1.5 py-0.5 rounded bg-indigo-950/80 text-indigo-300 border border-indigo-800/60">
                Track 03
              </span>
            </span>
          </div>
        </Link>

        <nav className="flex items-center space-x-4">
          <Link
            to="/dashboard"
            className={`flex items-center space-x-1.5 text-sm font-medium px-3 py-1.5 rounded-md transition-colors ${
              location.pathname === '/dashboard'
                ? 'bg-slate-800 text-indigo-400'
                : 'text-slate-400 hover:text-slate-200 hover:bg-slate-800/50'
            }`}
          >
            <LayoutDashboard className="w-4 h-4" />
            <span>Dashboard</span>
          </Link>

          <div className="h-4 w-px bg-slate-800" />

          {isAuthenticated ? (
            <button
              onClick={() => signOut()}
              className="text-sm font-medium text-slate-400 hover:text-slate-200 px-3 py-1.5 rounded-md hover:bg-slate-800 transition-colors"
            >
              Sign Out
            </button>
          ) : (
            <Link
              to="/login"
              className="flex items-center space-x-1.5 text-sm font-medium bg-indigo-600 hover:bg-indigo-500 text-white px-3.5 py-1.5 rounded-md shadow-sm transition-colors"
            >
              <LogIn className="w-4 h-4" />
              <span>Merchant Sign In</span>
            </Link>
          )}
        </nav>
      </div>
    </header>
  );
};
