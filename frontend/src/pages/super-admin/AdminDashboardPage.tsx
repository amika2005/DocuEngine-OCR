import { useTranslation } from 'react-i18next';
import { useQuery } from '@tanstack/react-query';
import { api } from '../../api/client';
import StatTile from '../../components/StatTile';
import VolumeChart, { type DailyPoint } from '../../components/VolumeChart';

interface AdminStats {
  companies: number;
  users: number;
  documents: number;
  documents_by_status: Record<string, number>;
  daily_volume: DailyPoint[];
  per_company: {
    id: string;
    name: string;
    slug: string;
    status: string;
    documents_total: number;
    users_count: number;
  }[];
  recent_audit: { action: string; target_type: string | null; created_at: string }[];
}

export default function AdminDashboardPage() {
  const { t } = useTranslation();
  const { data } = useQuery({
    queryKey: ['dashboard-admin'],
    queryFn: () => api<AdminStats>('/admin/stats'),
    refetchInterval: 30_000,
  });

  if (!data) return <p className="text-slate-500">{t('common.loading')}</p>;

  return (
    <div className="space-y-4">
      <h1 className="text-xl font-bold">{t('dashboard.title')}</h1>

      <div className="grid grid-cols-3 gap-4">
        <StatTile label={t('nav.companies')} value={data.companies} icon="🏢" to="/admin/companies" />
        <StatTile label={t('admin.users.title')} value={data.users} icon="👥" />
        <StatTile label={t('nav.documents')} value={data.documents} icon="📄" accent="blue" />
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <VolumeChart title={t('dashboard.volume7dGlobal')} data={data.daily_volume} />

        <div className="rounded-lg border border-slate-200 bg-white p-4">
          <h2 className="mb-2 text-sm font-medium text-slate-700">{t('dashboard.recentAudit')}</h2>
          <ul className="divide-y divide-slate-100">
            {data.recent_audit.map((entry, index) => (
              <li key={index} className="flex items-center gap-3 py-1.5 text-sm">
                <code className="text-xs text-slate-700">{entry.action}</code>
                <span className="text-xs text-slate-400">{entry.target_type ?? ''}</span>
                <span className="ml-auto shrink-0 text-xs text-slate-400">
                  {new Date(entry.created_at).toLocaleString()}
                </span>
              </li>
            ))}
            {data.recent_audit.length === 0 && (
              <li className="py-6 text-center text-sm text-slate-400">—</li>
            )}
          </ul>
        </div>
      </div>

      <div className="overflow-hidden rounded-lg border border-slate-200 bg-white">
        <table className="w-full text-sm">
          <thead className="bg-slate-100 text-left text-slate-600">
            <tr>
              <th className="px-4 py-2">{t('admin.companies.name')}</th>
              <th className="px-4 py-2">{t('admin.companies.status')}</th>
              <th className="px-4 py-2 text-right">{t('nav.documents')}</th>
              <th className="px-4 py-2 text-right">{t('admin.users.title')}</th>
            </tr>
          </thead>
          <tbody>
            {data.per_company.map((company) => (
              <tr key={company.id} className="border-t border-slate-100">
                <td className="px-4 py-2">
                  {company.name}
                  <span className="ml-2 font-mono text-xs text-slate-400">{company.slug}</span>
                </td>
                <td className="px-4 py-2">
                  <span
                    className={`rounded-full px-2 py-0.5 text-xs ${
                      company.status === 'active'
                        ? 'bg-green-100 text-green-800'
                        : 'bg-slate-100 text-slate-600'
                    }`}
                  >
                    {company.status}
                  </span>
                </td>
                <td className="px-4 py-2 text-right tabular-nums">{company.documents_total}</td>
                <td className="px-4 py-2 text-right tabular-nums">{company.users_count}</td>
              </tr>
            ))}
            {data.per_company.length === 0 && (
              <tr>
                <td colSpan={4} className="px-4 py-8 text-center text-slate-400">
                  —
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
