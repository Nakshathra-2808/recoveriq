import React from 'react';
import { Link } from 'react-router-dom';
import { Home } from 'lucide-react';

export const NotFoundPage: React.FC = () => {
  return (
    <div className="text-center py-20">
      <h1 className="text-4xl font-extrabold text-slate-100 tracking-tight">404</h1>
      <p className="text-slate-400 mt-2 text-sm">The requested page could not be found.</p>
      <Link
        to="/dashboard"
        className="inline-flex items-center gap-2 mt-6 px-4 py-2 rounded-lg bg-indigo-600 hover:bg-indigo-500 text-white text-sm font-medium transition-colors"
      >
        <Home className="w-4 h-4" />
        <span>Return to Dashboard</span>
      </Link>
    </div>
  );
};
