import { useCallback, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { api } from '../../api/client';
import type { Document, Page } from '../../api/types';
import { useEvents } from '../../api/useEvents';
import StatusBadge from '../../components/StatusBadge';
import PageViewer from '../../components/PageViewer';

export default function DocumentDetailPage() {
  const { id } = useParams<{ id: string }>();
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const [selectedPage, setSelectedPage] = useState(0);
  const [progress, setProgress] = useState<{ done: number; total: number } | null>(null);

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

  const onEvent = useCallback(
    (event: { topic: string; data: Record<string, unknown> }) => {
      if (event.topic.endsWith('.progress')) {
        setProgress({
          done: Number(event.data.pages_done ?? 0),
          total: Number(event.data.pages_total ?? 0),
        });
      }
      if (event.topic.endsWith('.status')) {
        queryClient.invalidateQueries({ queryKey: ['document', id] });
        queryClient.invalidateQueries({ queryKey: ['document-pages', id] });
        queryClient.invalidateQueries({ queryKey: ['document-markdown', id] });
      }
    },
    [id, queryClient],
  );
  useEvents(`document.${id}`, onEvent);

  if (!doc) return <p className="text-slate-500">{t('common.loading')}</p>;

  const processing = doc.status === 'queued' || doc.status === 'processing';
  const currentPage = pages?.[selectedPage];

  return (
    <div>
      <div className="mb-4 flex items-center gap-3">
        <h1 className="text-xl font-bold">{doc.original_filename}</h1>
        <StatusBadge status={doc.status} />
        <div className="ml-auto flex gap-2">
          {currentPage && (
            <Link
              to={`/pages/${currentPage.id}/correct`}
              className="rounded bg-amber-600 px-3 py-1.5 text-sm text-white hover:bg-amber-500"
            >
              {t('detail.edit')}
            </Link>
          )}
          {markdown != null && (
            <a
              href={`/api/v1/documents/${doc.id}/download`}
              className="rounded bg-slate-900 px-3 py-1.5 text-sm text-white hover:bg-slate-700"
            >
              {t('detail.download')}
            </a>
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
            <PageViewer src={`/api/v1/pages/${currentPage.id}/image`} />
          ) : (
            <p className="py-12 text-center text-slate-400">—</p>
          )}
        </section>

        <section className="rounded-lg border border-slate-200 bg-white p-3">
          <h2 className="mb-2 font-medium text-slate-700">{t('detail.markdown')}</h2>
          {markdown != null ? (
            <div className="markdown-body max-h-[70vh] overflow-auto text-sm">
              <ReactMarkdown remarkPlugins={[remarkGfm]}>{markdown}</ReactMarkdown>
            </div>
          ) : (
            <p className="py-12 text-center text-slate-400">
              {processing ? t('common.loading') : '—'}
            </p>
          )}
        </section>
      </div>
    </div>
  );
}
