import { Link } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { useQuery } from '@tanstack/react-query';
import { api } from '../../api/client';
import { useLiveInvalidate } from '../../api/useEvents';
import StatTile from '../../components/StatTile';
import StatusBadge from '../../components/StatusBadge';
import VolumeChart, { type DailyPoint } from '../../components/VolumeChart';

export interface UserDashboardData {
  documents_by_status: Record<string, number>;
  documents_today: number;
  processing_now: number;
  recent_documents: {
    id: string;
    original_filename: string;
    status: string;
    page_count: number;
    created_at: string;
  }[];
  my_corrections: { drafts: number; submitted: number };
  daily_volume: DailyPoint[];
}

export default function DashboardPage() {
  const { t } = useTranslation();

  const { data } = useQuery({
    queryKey: ['dashboard-user'],
    queryFn: () => api<UserDashboardData>('/dashboard/user'),
  });

  // Any tenant event (documents, corrections, admin actions) refreshes the tiles.
  useLiveInvalidate('', [['dashboard-user']]);

  if (!data) return <p className="text-slate-500">{t('common.loading')}</p>;

  const status = data.documents_by_status;
  const failed = (status.failed ?? 0) + (status.partially_failed ?? 0);

  return (
    <div className="space-y-4">
      <div className="flex items-center">
        <h1 className="text-xl font-bold">{t('dashboard.title')}</h1>
        <Link
          to="/scan"
          className="ml-auto rounded bg-slate-900 px-4 py-1.5 text-sm text-white hover:bg-slate-700"
        >
          📥 {t('nav.scan')}
        </Link>
      </div>

      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        <StatTile label={t('dashboard.today')} value={data.documents_today} icon="📅" accent="blue" />
        <StatTile
          label={t('dashboard.processing')}
          value={data.processing_now}
          icon="⚙️"
          accent={data.processing_now > 0 ? 'amber' : 'default'}
        />
        <StatTile
          label={t('documents.statusValues.completed')}
          value={status.completed ?? 0}
          icon="✅"
          accent="green"
          to="/documents"
        />
        <StatTile
          label={t('dashboard.failed')}
          value={failed}
          icon="⚠️"
          accent={failed > 0 ? 'red' : 'default'}
          to="/documents"
        />
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <VolumeChart title={t('dashboard.volume7d')} data={data.daily_volume} />

        <div className="rounded-lg border border-slate-200 bg-white p-4">
          <div className="mb-2 flex items-baseline justify-between">
            <h2 className="text-sm font-medium text-slate-700">{t('dashboard.recent')}</h2>
            <Link to="/documents" className="text-xs text-blue-700 hover:underline">
              {t('dashboard.viewAll')}
            </Link>
          </div>
          <ul className="divide-y divide-slate-100">
            {data.recent_documents.map((doc) => (
              <li key={doc.id} className="flex items-center gap-3 py-2 text-sm">
                <Link
                  to={`/documents/${doc.id}`}
                  className="min-w-0 flex-1 truncate text-blue-700 hover:underline"
                >
                  {doc.original_filename}
                </Link>
                <StatusBadge status={doc.status} />
                <span className="w-24 shrink-0 text-right text-xs text-slate-400">
                  {new Date(doc.created_at).toLocaleDateString()}
                </span>
              </li>
            ))}
            {data.recent_documents.length === 0 && (
              <li className="py-6 text-center text-sm text-slate-400">{t('documents.empty')}</li>
            )}
          </ul>
        </div>
      </div>

      {(data.my_corrections.drafts > 0 || data.my_corrections.submitted > 0) && (
        <Link
          to="/corrections"
          className="block rounded-lg border border-amber-200 bg-amber-50 p-3 text-sm text-amber-900 hover:bg-amber-100"
        >
          ✏️ {t('dashboard.myCorrections', {
            drafts: data.my_corrections.drafts,
            submitted: data.my_corrections.submitted,
          })}
        </Link>
      )}
    </div>
  );
}
