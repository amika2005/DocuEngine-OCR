import { Link } from 'react-router-dom';
import { AlertTriangle, CalendarDays, Cog, PenLine, Users } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { useQuery } from '@tanstack/react-query';
import { api } from '../../api/client';
import { useLiveInvalidate } from '../../api/useEvents';
import StatTile from '../../components/StatTile';
import StatusBadge from '../../components/StatusBadge';
import VolumeChart from '../../components/VolumeChart';
import type { UserDashboardData } from '../user/DashboardPage';

interface CompanyDashboardData extends UserDashboardData {
  users_count: number;
  devices: { id: string; name: string; status: string; last_seen_at: string | null }[];
  corrections_awaiting_approval: number;
  latest_training_run: { id: string; status: string; finished_at: string | null } | null;
  active_model: string | null;
}

function deviceOnline(lastSeen: string | null): boolean {
  if (!lastSeen) return false;
  return Date.now() - new Date(lastSeen).getTime() < 10 * 60 * 1000;
}

export default function CompanyDashboardPage() {
  const { t } = useTranslation();

  const { data } = useQuery({
    queryKey: ['dashboard-company'],
    queryFn: () => api<CompanyDashboardData>('/dashboard/company'),
  });

  // Any tenant event (documents, users, devices, corrections, training,
  // model activation) refreshes the whole dashboard.
  useLiveInvalidate('', [['dashboard-company']]);

  if (!data) return <p className="text-slate-500">{t('common.loading')}</p>;

  const status = data.documents_by_status;
  const failed = (status.failed ?? 0) + (status.partially_failed ?? 0);

  return (
    <div className="space-y-4">
      <h1 className="text-xl font-bold">{t('dashboard.title')}</h1>

      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        <StatTile label={t('dashboard.today')} value={data.documents_today} icon={CalendarDays} accent="blue" />
        <StatTile
          label={t('dashboard.processing')}
          value={data.processing_now}
          icon={Cog}
          accent={data.processing_now > 0 ? 'amber' : 'default'}
        />
        <StatTile
          label={t('dashboard.failed')}
          value={failed}
          icon={AlertTriangle}
          accent={failed > 0 ? 'red' : 'default'}
          to="/documents"
        />
        <StatTile
          label={t('dashboard.awaitingApproval')}
          value={data.corrections_awaiting_approval}
          icon={PenLine}
          accent={data.corrections_awaiting_approval > 0 ? 'amber' : 'default'}
          to="/corrections"
        />
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <VolumeChart title={t('dashboard.volume7d')} data={data.daily_volume} />

        <div className="rounded-lg border border-slate-200 bg-white p-4">
          <div className="mb-2 flex items-baseline justify-between">
            <h2 className="text-sm font-medium text-slate-700">{t('dashboard.devices')}</h2>
            <Link to="/company/devices" className="text-xs text-blue-700 hover:underline">
              {t('dashboard.viewAll')}
            </Link>
          </div>
          <ul className="divide-y divide-slate-100">
            {data.devices.map((device) => {
              const online = deviceOnline(device.last_seen_at);
              return (
                <li key={device.id} className="flex items-center gap-3 py-2 text-sm">
                  <span
                    className={`h-2 w-2 shrink-0 rounded-full ${online ? 'bg-green-500' : 'bg-slate-300'}`}
                    title={online ? t('dashboard.online') : t('dashboard.offline')}
                  />
                  <span className="min-w-0 flex-1 truncate">{device.name}</span>
                  <span className="text-xs text-slate-400">
                    {device.last_seen_at
                      ? new Date(device.last_seen_at).toLocaleString()
                      : t('dashboard.neverSeen')}
                  </span>
                </li>
              );
            })}
            {data.devices.length === 0 && (
              <li className="py-6 text-center text-sm text-slate-400">
                <Link to="/company/devices" className="text-blue-700 hover:underline">
                  {t('admin.devices.add')}
                </Link>
              </li>
            )}
          </ul>
        </div>
      </div>

      <div className="grid gap-4 lg:grid-cols-3">
        <StatTile label={t('nav.users')} value={data.users_count} icon={Users} to="/company/users" />
        <div className="rounded-lg border border-slate-200 bg-white p-4">
          <p className="text-xs font-medium text-slate-500">{t('dashboard.activeModel')}</p>
          <p className="mt-1 truncate text-sm font-medium text-slate-800">
            {data.active_model ?? '—'}
          </p>
        </div>
        <Link to="/company/training" className="block">
          <div className="h-full rounded-lg border border-slate-200 bg-white p-4 hover:shadow-sm">
            <p className="text-xs font-medium text-slate-500">{t('dashboard.lastTraining')}</p>
            <p className="mt-1 text-sm font-medium text-slate-800">
              {data.latest_training_run
                ? `${data.latest_training_run.status}${
                    data.latest_training_run.finished_at
                      ? ` — ${new Date(data.latest_training_run.finished_at).toLocaleDateString()}`
                      : ''
                  }`
                : t('dashboard.noTraining')}
            </p>
          </div>
        </Link>
      </div>

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
  );
}
