import { useTranslation } from 'react-i18next';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { api } from '../../api/client';
import type { Correction } from '../../api/types';
import { useAuth } from '../../auth/AuthContext';

export default function CorrectionsPage() {
  const { t } = useTranslation();
  const { me } = useAuth();
  const queryClient = useQueryClient();

  const { data: corrections } = useQuery({
    queryKey: ['corrections'],
    queryFn: () => api<Correction[]>('/corrections'),
  });

  async function act(id: string, action: 'approve' | 'reject') {
    await api(`/corrections/${id}/${action}`, { method: 'POST' });
    queryClient.invalidateQueries({ queryKey: ['corrections'] });
  }

  return (
    <div>
      <h1 className="mb-4 text-xl font-bold">{t('corrections.title')}</h1>
      <div className="space-y-3">
        {corrections?.map((correction) => (
          <div key={correction.id} className="rounded-lg border border-slate-200 bg-white p-4">
            <div className="mb-2 flex items-center gap-3 text-sm">
              <span className="rounded-full bg-slate-100 px-2 py-0.5 text-xs">
                {t(`corrections.status.${correction.status}`, correction.status)}
              </span>
              <span className="text-slate-400">
                {new Date(correction.created_at).toLocaleString()}
              </span>
              {me?.role === 'company_admin' && correction.status === 'submitted' && (
                <span className="ml-auto flex gap-2">
                  <button
                    onClick={() => act(correction.id, 'approve')}
                    className="rounded bg-green-600 px-3 py-1 text-xs text-white hover:bg-green-500"
                  >
                    {t('corrections.approve')}
                  </button>
                  <button
                    onClick={() => act(correction.id, 'reject')}
                    className="rounded bg-red-600 px-3 py-1 text-xs text-white hover:bg-red-500"
                  >
                    {t('corrections.reject')}
                  </button>
                </span>
              )}
            </div>
            <div className="grid grid-cols-2 gap-3 text-xs">
              <pre className="max-h-40 overflow-auto rounded bg-red-50 p-2 whitespace-pre-wrap">
                {correction.original_markdown}
              </pre>
              <pre className="max-h-40 overflow-auto rounded bg-green-50 p-2 whitespace-pre-wrap">
                {correction.corrected_markdown}
              </pre>
            </div>
          </div>
        ))}
        {corrections?.length === 0 && <p className="text-slate-400">—</p>}
      </div>
    </div>
  );
}
