import { useTranslation } from 'react-i18next';
import { useQuery } from '@tanstack/react-query';
import { api } from '../../api/client';

interface Stats {
  companies: number;
  users: number;
  documents: number;
  documents_by_status: Record<string, number>;
}

export default function StatsPage() {
  const { t } = useTranslation();
  const { data } = useQuery({ queryKey: ['stats'], queryFn: () => api<Stats>('/admin/stats') });

  return (
    <div>
      <h1 className="mb-4 text-xl font-bold">{t('nav.stats')}</h1>
      <div className="grid grid-cols-3 gap-4">
        {[
          [t('nav.companies'), data?.companies],
          [t('admin.users.title'), data?.users],
          [t('nav.documents'), data?.documents],
        ].map(([label, value]) => (
          <div key={String(label)} className="rounded-lg border border-slate-200 bg-white p-6 text-center">
            <p className="text-3xl font-bold">{value ?? '—'}</p>
            <p className="mt-1 text-sm text-slate-500">{label}</p>
          </div>
        ))}
      </div>
      {data && (
        <div className="mt-6 rounded-lg border border-slate-200 bg-white p-4">
          <table className="w-full text-sm">
            <tbody>
              {Object.entries(data.documents_by_status).map(([status, count]) => (
                <tr key={status} className="border-t border-slate-100 first:border-t-0">
                  <td className="py-1.5">{t(`documents.statusValues.${status}`, status)}</td>
                  <td className="py-1.5 text-right font-mono">{count}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
