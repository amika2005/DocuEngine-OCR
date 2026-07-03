import { useTranslation } from 'react-i18next';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { api } from '../../api/client';
import { useLiveInvalidate } from '../../api/useEvents';
import type { ModelVersion, TrainingRun } from '../../api/types';

export default function TrainingPage() {
  const { t } = useTranslation();
  const queryClient = useQueryClient();

  const { data: runs } = useQuery({
    queryKey: ['training-runs'],
    queryFn: () => api<TrainingRun[]>('/company/training-runs'),
  });
  const { data: versions } = useQuery({
    queryKey: ['model-versions'],
    queryFn: () => api<ModelVersion[]>('/company/model-versions'),
  });
  useLiveInvalidate(['training.', 'models.'], [['training-runs'], ['model-versions']]);

  async function trigger() {
    await api('/company/training-runs', { method: 'POST' });
    queryClient.invalidateQueries({ queryKey: ['training-runs'] });
  }

  async function activate(id: string) {
    await api(`/company/model-versions/${id}/activate`, { method: 'POST' });
    queryClient.invalidateQueries({ queryKey: ['model-versions'] });
  }

  return (
    <div>
      <div className="mb-4 flex items-center">
        <h1 className="text-xl font-bold">{t('admin.training.title')}</h1>
        <button onClick={trigger} className="ml-auto rounded bg-slate-900 px-4 py-1.5 text-sm text-white hover:bg-slate-700">
          {t('admin.training.trigger')}
        </button>
      </div>

      <div className="mb-6 overflow-hidden rounded-lg border border-slate-200 bg-white">
        <table className="w-full text-sm">
          <thead className="bg-slate-100 text-left text-slate-600">
            <tr>
              <th className="px-4 py-2">{t('admin.training.status')}</th>
              <th className="px-4 py-2">{t('admin.training.started')}</th>
              <th className="px-4 py-2">{t('admin.training.finished')}</th>
              <th className="px-4 py-2">Eval</th>
            </tr>
          </thead>
          <tbody>
            {runs?.map((run) => (
              <tr key={run.id} className="border-t border-slate-100">
                <td className="px-4 py-2">{run.status}</td>
                <td className="px-4 py-2">{run.started_at ? new Date(run.started_at).toLocaleString() : '—'}</td>
                <td className="px-4 py-2">{run.finished_at ? new Date(run.finished_at).toLocaleString() : '—'}</td>
                <td className="px-4 py-2 text-xs">
                  {Object.keys(run.eval_report).length > 0 ? JSON.stringify(run.eval_report) : '—'}
                </td>
              </tr>
            ))}
            {runs?.length === 0 && (
              <tr><td colSpan={4} className="px-4 py-6 text-center text-slate-400">—</td></tr>
            )}
          </tbody>
        </table>
      </div>

      <h2 className="mb-2 font-medium text-slate-700">Models</h2>
      <div className="overflow-hidden rounded-lg border border-slate-200 bg-white">
        <table className="w-full text-sm">
          <tbody>
            {versions?.map((version) => (
              <tr key={version.id} className="border-t border-slate-100">
                <td className="px-4 py-2">{version.name}</td>
                <td className="px-4 py-2">{version.kind}</td>
                <td className="px-4 py-2">
                  <span className={`rounded-full px-2 py-0.5 text-xs ${version.status === 'active' ? 'bg-green-100 text-green-800' : 'bg-slate-100'}`}>
                    {version.status}
                  </span>
                </td>
                <td className="px-4 py-2 text-right">
                  {(version.status === 'candidate' || version.status === 'retired') && (
                    <button onClick={() => activate(version.id)} className="text-xs text-blue-700 hover:underline">
                      {version.status === 'retired' ? t('admin.training.rollback') : t('admin.training.activate')}
                    </button>
                  )}
                </td>
              </tr>
            ))}
            {versions?.length === 0 && (
              <tr><td className="px-4 py-6 text-center text-slate-400">—</td></tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
