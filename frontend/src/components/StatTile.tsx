import type { ReactNode } from 'react';
import { Link } from 'react-router-dom';

interface Props {
  label: string;
  value: ReactNode;
  icon?: string;
  to?: string; // optional drill-down link
  accent?: 'default' | 'blue' | 'green' | 'red' | 'amber';
}

const ACCENTS: Record<NonNullable<Props['accent']>, string> = {
  default: 'text-slate-900',
  blue: 'text-blue-700',
  green: 'text-green-700',
  red: 'text-red-700',
  amber: 'text-amber-700',
};

export default function StatTile({ label, value, icon, to, accent = 'default' }: Props) {
  const body = (
    <div className="h-full rounded-lg border border-slate-200 bg-white p-4 transition-shadow hover:shadow-sm">
      <div className="flex items-center justify-between">
        <p className="text-xs font-medium text-slate-500">{label}</p>
        {icon && (
          <span className="text-base opacity-60" aria-hidden>
            {icon}
          </span>
        )}
      </div>
      <p className={`mt-1 text-3xl font-bold tabular-nums ${ACCENTS[accent]}`}>{value}</p>
    </div>
  );
  return to ? <Link to={to}>{body}</Link> : body;
}
