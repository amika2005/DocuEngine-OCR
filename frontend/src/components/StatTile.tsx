import type { ReactNode } from 'react';
import { Link } from 'react-router-dom';
import type { LucideIcon } from 'lucide-react';

interface Props {
  label: string;
  value: ReactNode;
  icon?: LucideIcon;
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

export default function StatTile({ label, value, icon: Icon, to, accent = 'default' }: Props) {
  const body = (
    <div className="h-full rounded-lg border border-slate-200 bg-white p-4 transition-shadow hover:shadow-sm">
      <div className="flex items-center justify-between">
        <p className="text-sm font-medium text-slate-500">{label}</p>
        {Icon && <Icon className="h-5 w-5 text-slate-400" strokeWidth={1.8} aria-hidden />}
      </div>
      <p className={`mt-1 text-3xl font-bold tabular-nums ${ACCENTS[accent]}`}>{value}</p>
    </div>
  );
  return to ? <Link to={to}>{body}</Link> : body;
}
