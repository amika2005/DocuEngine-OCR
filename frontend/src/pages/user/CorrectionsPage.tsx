import { useMemo } from 'react';
import { useTranslation } from 'react-i18next';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { api } from '../../api/client';
import { useLiveInvalidate } from '../../api/useEvents';
import type { Correction } from '../../api/types';
import { useAuth } from '../../auth/AuthContext';

function diffLines(original: string, corrected: string) {
  const oldLines = original.split('\n');
  const newLines = corrected.split('\n');
  const changes: { old: string; new: string }[] = [];
  const max = Math.max(oldLines.length, newLines.length);
  for (let i = 0; i < max; i++) {
    const o = oldLines[i] ?? '';
    const n = newLines[i] ?? '';
    if (o !== n) changes.push({ old: o, new: n });
  }
  return changes;
}

const statusColor: Record<string, string> = {
  draft: 'bg-slate-100 text-slate-600',
  submitted: 'bg-amber-100 text-amber-700',
  approved: 'bg-green-100 text-green-700',
  rejected: 'bg-red-100 text-red-700',
  used_in_training: 'bg-blue-100 text-blue-700',
};

function CorrectionCard({
  correction,
  canAdmin,
  onAct,
}: {
  correction: Correction;
  canAdmin: boolean;
  onAct: (id: string, action: 'approve' | 'reject') => void;
}) {
  const { t } = useTranslation();
  const changes = useMemo(
    () => diffLines(correction.original_markdown, correction.corrected_markdown),
    [correction.original_markdown, correction.corrected_markdown],
  );

  return (
    <div className="rounded-lg border border-slate-200 bg-white">
      <div className="flex items-center gap-3 border-b border-slate-100 px-4 py-2.5">
        <span
          className={`rounded-full px-2.5 py-0.5 text-xs font-medium ${statusColor[correction.status] ?? 'bg-slate-100 text-slate-600'}`}
        >
          {t(`corrections.status.${correction.status}`, correction.status)}
        </span>
        <span className="text-xs text-slate-400">
          {new Date(correction.created_at).toLocaleString()}
        </span>
        {correction.region_index != null && (
          <span className="text-xs text-slate-400">
            {t('corrections.region', { index: correction.region_index + 1 })}
          </span>
        )}
        {canAdmin && correction.status === 'submitted' && (
          <span className="ml-auto flex gap-2">
            <button
              onClick={() => onAct(correction.id, 'approve')}
              className="rounded bg-green-600 px-3 py-1 text-xs text-white hover:bg-green-500"
            >
              {t('corrections.approve')}
            </button>
            <button
              onClick={() => onAct(correction.id, 'reject')}
              className="rounded bg-red-600 px-3 py-1 text-xs text-white hover:bg-red-500"
            >
              {t('corrections.reject')}
            </button>
          </span>
        )}
      </div>

      <div className="divide-y divide-slate-50 px-4 py-2">
        {changes.length === 0 && (
          <p className="py-2 text-xs text-slate-400">{t('corrections.noChanges')}</p>
        )}
        {changes.map((change, i) => (
          <div key={i} className="flex gap-3 py-1.5 text-sm">
            <div className="min-w-0 flex-1">
              {change.old && (
                <span className="inline rounded bg-red-50 px-1.5 py-0.5 text-red-700 line-through">
                  {change.old}
                </span>
              )}
            </div>
            <span className="shrink-0 text-slate-300">→</span>
            <div className="min-w-0 flex-1">
              {change.new && (
                <span className="inline rounded bg-green-50 px-1.5 py-0.5 text-green-700">
                  {change.new}
                </span>
              )}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

export default function CorrectionsPage() {
  const { t } = useTranslation();
  const { me } = useAuth();
  const queryClient = useQueryClient();

  const { data: corrections } = useQuery({
    queryKey: ['corrections'],
    queryFn: () => api<Correction[]>('/corrections'),
  });
  useLiveInvalidate('corrections.', [['corrections']]);

  async function act(id: string, action: 'approve' | 'reject') {
    await api(`/corrections/${id}/${action}`, { method: 'POST' });
    queryClient.invalidateQueries({ queryKey: ['corrections'] });
  }

  const canAdmin = me?.role === 'company_admin';

  return (
    <div>
      <h1 className="mb-4 text-xl font-bold">{t('corrections.title')}</h1>
      <div className="space-y-3">
        {corrections?.map((correction) => (
          <CorrectionCard
            key={correction.id}
            correction={correction}
            canAdmin={canAdmin}
            onAct={act}
          />
        ))}
        {corrections?.length === 0 && <p className="text-slate-400">—</p>}
      </div>
    </div>
  );
}
