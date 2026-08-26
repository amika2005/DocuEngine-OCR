import { useMemo } from 'react';
import { Link } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { api } from '../../api/client';
import { useLiveInvalidate } from '../../api/useEvents';
import type { Correction } from '../../api/types';
import { useAuth } from '../../auth/AuthContext';
import {
  commonAffix,
  diffCorrectionMarkdown,
  type CorrectionChange,
} from '../../lib/correctionDiff';

const MAX_CHANGES = 40;

const statusColor: Record<string, string> = {
  draft: 'bg-slate-100 text-slate-600',
  submitted: 'bg-amber-100 text-amber-700',
  approved: 'bg-green-100 text-green-700',
  rejected: 'bg-red-100 text-red-700',
  used_in_training: 'bg-blue-100 text-blue-700',
};

function ChangeSnippet({ change }: { change: CorrectionChange }) {
  const { prefix, oldMid, newMid, suffix } = commonAffix(change.oldText, change.newText);
  const showOld = Boolean(change.oldText);
  const showNew = Boolean(change.newText);

  return (
    <div className="flex flex-wrap items-baseline gap-x-2 gap-y-1 text-sm">
      {showOld && (
        <span className="min-w-0 whitespace-pre-wrap break-words text-slate-700">
          {prefix}
          {oldMid ? (
            <span className="rounded bg-red-50 px-0.5 text-red-700 line-through">{oldMid}</span>
          ) : null}
          {suffix}
        </span>
      )}
      {showOld && showNew && <span className="shrink-0 text-slate-300">→</span>}
      {showNew && (
        <span className="min-w-0 whitespace-pre-wrap break-words text-slate-700">
          {prefix}
          {newMid ? (
            <span className="rounded bg-green-50 px-0.5 text-green-800">{newMid}</span>
          ) : null}
          {suffix}
        </span>
      )}
    </div>
  );
}

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
    () => diffCorrectionMarkdown(correction.original_markdown, correction.corrected_markdown),
    [correction.original_markdown, correction.corrected_markdown],
  );
  const visible = changes.slice(0, MAX_CHANGES);
  const hiddenCount = changes.length - visible.length;
  const documentTo =
    correction.document_id != null
      ? `/documents/${correction.document_id}${
          correction.page_number != null ? `?page=${correction.page_number}` : ''
        }`
      : null;

  return (
    <div className="rounded-lg border border-slate-200 bg-white">
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1.5 border-b border-slate-100 px-4 py-2.5">
        <span
          className={`rounded-full px-2.5 py-0.5 text-xs font-medium ${statusColor[correction.status] ?? 'bg-slate-100 text-slate-600'}`}
        >
          {t(`corrections.status.${correction.status}`, correction.status)}
        </span>
        {documentTo && (correction.filename || correction.page_number != null) && (
          <Link
            to={documentTo}
            className="min-w-0 truncate text-xs font-medium text-slate-700 hover:text-slate-900 hover:underline"
          >
            {t('corrections.where', {
              file: correction.filename || t('corrections.document'),
              page: correction.page_number ?? '—',
            })}
          </Link>
        )}
        <span className="text-xs text-slate-400">{new Date(correction.created_at).toLocaleString()}</span>
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
        {documentTo && !(canAdmin && correction.status === 'submitted') && (
          <Link
            to={documentTo}
            className="ml-auto text-xs text-slate-500 hover:text-slate-800 hover:underline"
          >
            {t('corrections.openDocument')}
          </Link>
        )}
      </div>

      <div className="divide-y divide-slate-50 px-4 py-1">
        {changes.length === 0 && (
          <p className="py-2 text-xs text-slate-400">{t('corrections.noChanges')}</p>
        )}
        {visible.map((change, i) => (
          <div key={i} className="py-2">
            {(change.column || change.row != null || change.kind === 'cell') && (
              <p className="mb-1 text-[11px] font-medium tracking-wide text-slate-400">
                {change.kind === 'cell' ? t('corrections.changedCell') : t('corrections.changedLine')}
                {change.column ? ` · ${change.column}` : ''}
                {change.row != null ? ` · ${t('corrections.row', { n: change.row })}` : ''}
              </p>
            )}
            <ChangeSnippet change={change} />
          </div>
        ))}
        {hiddenCount > 0 && (
          <p className="py-2 text-xs text-slate-400">{t('corrections.moreChanges', { count: hiddenCount })}</p>
        )}
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
    queryFn: async () => {
      const all = await api<Correction[]>('/corrections');
      return all.filter((c) => c.original_markdown !== c.corrected_markdown);
    },
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
