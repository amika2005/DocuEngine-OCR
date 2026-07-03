import { useCallback, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { api, downloadFile } from '../../api/client';
import type { Document, MasterMatch, Page } from '../../api/types';
import { useEvents } from '../../api/useEvents';
import StatusBadge from '../../components/StatusBadge';
import PageViewer from '../../components/PageViewer';
import MatchableMarkdown from '../../components/MatchableMarkdown';
import MatchPopup from '../../components/MatchPopup';

export default function DocumentDetailPage() {
  const { id } = useParams<{ id: string }>();
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const [selectedPage, setSelectedPage] = useState(0);
  const [progress, setProgress] = useState<{ done: number; total: number } | null>(null);
  const [popup, setPopup] = useState<{ match: MasterMatch; anchor: HTMLElement } | null>(null);
  const [linkBusy, setLinkBusy] = useState(false);

  const { data: doc } = useQuery({
    queryKey: ['document', id],
    queryFn: () => api<Document>(`/documents/${id}`),
  });
  const { data: pages } = useQuery({
    queryKey: ['document-pages', id],
    queryFn: () => api<Page[]>(`/documents/${id}/pages`),
    enabled: !!doc && doc.status !== 'uploaded',
  });
  const { data: markdown } = useQuery({
    queryKey: ['document-markdown', id],
    queryFn: () => api<string>(`/documents/${id}/markdown`),
    enabled: !!doc && (doc.status === 'completed' || doc.status === 'partially_failed'),
  });

  const currentPage = pages?.[selectedPage];
  const { data: matches } = useQuery({
    queryKey: ['page-matches', currentPage?.id],
    queryFn: () => api<MasterMatch[]>(`/pages/${currentPage!.id}/matches`),
    enabled: !!currentPage,
  });

  const invalidateAll = useCallback(() => {
    queryClient.invalidateQueries({ queryKey: ['document', id] });
    queryClient.invalidateQueries({ queryKey: ['document-pages', id] });
    queryClient.invalidateQueries({ queryKey: ['document-markdown', id] });
    queryClient.invalidateQueries({ queryKey: ['page-matches'] });
  }, [id, queryClient]);

  const onEvent = useCallback(
    (event: { topic: string; data: Record<string, unknown> }) => {
      if (event.topic.endsWith('.progress')) {
        setProgress({
          done: Number(event.data.pages_done ?? 0),
          total: Number(event.data.pages_total ?? 0),
        });
        return;
      }
      if (event.topic.startsWith(`document.${id}.`) || event.topic === 'matches.changed') {
        invalidateAll();
      }
    },
    [id, invalidateAll],
  );
  useEvents([`document.${id}`, 'matches.changed'], onEvent);

  async function actOnMatch(action: 'link' | 'dismiss') {
    if (!popup) return;
    setLinkBusy(true);
    try {
      await api(`/matches/${popup.match.id}/${action}`, { method: 'POST' });
      setPopup(null);
      invalidateAll();
    } finally {
      setLinkBusy(false);
    }
  }

  async function rematch() {
    await api(`/documents/${id}/rematch`, { method: 'POST' });
  }

  if (!doc) return <p className="text-slate-500">{t('common.loading')}</p>;

  const processing = doc.status === 'queued' || doc.status === 'processing';
  const suggestedCount = matches?.filter((match) => match.status === 'suggested').length ?? 0;

  return (
    <div>
      <div className="mb-4 flex items-center gap-3">
        <h1 className="min-w-0 flex-1 truncate text-xl font-bold">{doc.original_filename}</h1>
        <StatusBadge status={doc.status} />
        {suggestedCount > 0 && (
          <span className="rounded-full bg-green-100 px-2 py-0.5 text-xs text-green-800">
            ✓ {t('masters.matchCount', { count: suggestedCount })}
          </span>
        )}
        <div className="flex shrink-0 gap-2">
          <button
            onClick={rematch}
            className="rounded border border-slate-300 bg-white px-3 py-1.5 text-sm hover:bg-slate-50"
            title={t('masters.rematchHint')}
          >
            {t('masters.rematch')}
          </button>
          {currentPage && (
            <Link
              to={`/pages/${currentPage.id}/correct`}
              className="rounded bg-amber-600 px-3 py-1.5 text-sm text-white hover:bg-amber-500"
            >
              {t('detail.edit')}
            </Link>
          )}
          {markdown != null && (
            <button
              onClick={() =>
                downloadFile(
                  `/documents/${doc.id}/download`,
                  `${doc.original_filename.replace(/\.[^.]+$/, '')}.md`,
                )
              }
              className="rounded bg-slate-900 px-3 py-1.5 text-sm text-white hover:bg-slate-700"
            >
              {t('detail.download')}
            </button>
          )}
        </div>
      </div>

      {processing && (
        <div className="mb-4 rounded-lg border border-blue-200 bg-blue-50 p-4">
          <p className="text-sm text-blue-800">
            {progress
              ? t('detail.progress', { done: progress.done, total: progress.total })
              : t('common.loading')}
          </p>
          {progress && progress.total > 0 && (
            <div className="mt-2 h-2 overflow-hidden rounded bg-blue-100">
              <div
                className="h-full bg-blue-600 transition-all"
                style={{ width: `${(progress.done / progress.total) * 100}%` }}
              />
            </div>
          )}
        </div>
      )}

      {doc.error_message && (
        <p className="mb-4 rounded border border-red-200 bg-red-50 p-3 text-sm text-red-700">
          {doc.error_message}
        </p>
      )}

      <div className="grid grid-cols-2 gap-4">
        <section className="rounded-lg border border-slate-200 bg-white p-3">
          <div className="mb-2 flex items-center justify-between">
            <h2 className="font-medium text-slate-700">{t('detail.originalImage')}</h2>
            {pages && pages.length > 1 && (
              <select
                value={selectedPage}
                onChange={(event) => setSelectedPage(Number(event.target.value))}
                className="rounded border border-slate-300 px-2 py-1 text-sm"
              >
                {pages.map((page, index) => (
                  <option key={page.id} value={index}>
                    p.{page.page_number}
                  </option>
                ))}
              </select>
            )}
          </div>
          {currentPage ? (
            <PageViewer path={`/pages/${currentPage.id}/image`} />
          ) : (
            <p className="py-12 text-center text-slate-400">—</p>
          )}
        </section>

        <section className="rounded-lg border border-slate-200 bg-white p-3">
          <h2 className="mb-2 font-medium text-slate-700">{t('detail.markdown')}</h2>
          {markdown != null ? (
            <div className="markdown-body max-h-[70vh] overflow-auto text-sm">
              <MatchableMarkdown
                markdown={markdown}
                matches={matches ?? []}
                onMatchClick={(match, anchor) => setPopup({ match, anchor })}
              />
            </div>
          ) : (
            <p className="py-12 text-center text-slate-400">
              {processing ? t('common.loading') : '—'}
            </p>
          )}
        </section>
      </div>

      {popup && (
        <MatchPopup
          match={popup.match}
          anchor={popup.anchor}
          busy={linkBusy}
          onLink={() => actOnMatch('link')}
          onDismiss={() => actOnMatch('dismiss')}
          onClose={() => setPopup(null)}
        />
      )}
    </div>
  );
}
