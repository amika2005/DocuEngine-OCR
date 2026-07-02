import { useCallback, useState } from 'react';
import { Link } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { api } from '../../api/client';
import type { Document, DocumentList } from '../../api/types';
import { useEvents } from '../../api/useEvents';
import StatusBadge from '../../components/StatusBadge';
import DocumentThumbnail from '../../components/DocumentThumbnail';

type ViewMode = 'list' | 'grid';

export default function DocumentsPage() {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const [page, setPage] = useState(1);
  const [search, setSearch] = useState('');
  const [view, setView] = useState<ViewMode>(
    (localStorage.getItem('docuengine-view') as ViewMode) ?? 'list',
  );

  const { data } = useQuery({
    queryKey: ['documents', page, search],
    queryFn: () =>
      api<DocumentList>(
        `/documents?page=${page}&page_size=24${search ? `&q=${encodeURIComponent(search)}` : ''}`,
      ),
  });

  const refresh = useCallback(
    () => queryClient.invalidateQueries({ queryKey: ['documents'] }),
    [queryClient],
  );
  useEvents('document.', refresh);

  function switchView(mode: ViewMode) {
    setView(mode);
    localStorage.setItem('docuengine-view', mode);
  }

  const totalPages = data ? Math.max(1, Math.ceil(data.total / data.page_size)) : 1;

  return (
    <div>
      <div className="mb-4 flex items-center gap-3">
        <h1 className="text-xl font-bold">{t('documents.title')}</h1>
        <input
          placeholder={t('documents.search')}
          value={search}
          onChange={(event) => {
            setSearch(event.target.value);
            setPage(1);
          }}
          className="ml-auto w-64 rounded border border-slate-300 px-3 py-1.5 text-sm"
        />
        <div className="flex overflow-hidden rounded-md border border-slate-300 text-sm">
          <button
            onClick={() => switchView('list')}
            title={t('documents.listView')}
            className={`px-3 py-1.5 ${view === 'list' ? 'bg-slate-900 text-white' : 'bg-white text-slate-600 hover:bg-slate-100'}`}
          >
            ☰
          </button>
          <button
            onClick={() => switchView('grid')}
            title={t('documents.gridView')}
            className={`px-3 py-1.5 ${view === 'grid' ? 'bg-slate-900 text-white' : 'bg-white text-slate-600 hover:bg-slate-100'}`}
          >
            ▦
          </button>
        </div>
        <Link
          to="/scan"
          className="rounded bg-slate-900 px-4 py-1.5 text-sm text-white hover:bg-slate-700"
        >
          {t('nav.scan')}
        </Link>
      </div>

      {view === 'list' ? (
        <ListView documents={data?.items ?? []} empty={data?.items.length === 0} />
      ) : (
        <GridView documents={data?.items ?? []} empty={data?.items.length === 0} />
      )}

      {totalPages > 1 && (
        <div className="mt-4 flex justify-center gap-2 text-sm">
          {Array.from({ length: totalPages }, (_, index) => index + 1).map((p) => (
            <button
              key={p}
              onClick={() => setPage(p)}
              className={`rounded px-3 py-1 ${p === page ? 'bg-slate-900 text-white' : 'bg-white hover:bg-slate-100'}`}
            >
              {p}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

function ListView({ documents, empty }: { documents: Document[]; empty?: boolean }) {
  const { t } = useTranslation();
  return (
    <div className="overflow-hidden rounded-lg border border-slate-200 bg-white">
      <table className="w-full text-sm">
        <thead className="bg-slate-100 text-left text-slate-600">
          <tr>
            <th className="px-4 py-2">{t('documents.filename')}</th>
            <th className="px-4 py-2">{t('documents.status')}</th>
            <th className="px-4 py-2">{t('documents.pages')}</th>
            <th className="px-4 py-2">{t('documents.date')}</th>
          </tr>
        </thead>
        <tbody>
          {documents.map((doc) => (
            <tr key={doc.id} className="border-t border-slate-100 hover:bg-slate-50">
              <td className="px-4 py-2">
                <Link to={`/documents/${doc.id}`} className="text-blue-700 hover:underline">
                  {doc.original_filename}
                </Link>
              </td>
              <td className="px-4 py-2">
                <StatusBadge status={doc.status} />
              </td>
              <td className="px-4 py-2">{doc.page_count || '—'}</td>
              <td className="px-4 py-2">{new Date(doc.created_at).toLocaleString()}</td>
            </tr>
          ))}
          {empty && (
            <tr>
              <td colSpan={4} className="px-4 py-8 text-center text-slate-400">
                {t('documents.empty')}
              </td>
            </tr>
          )}
        </tbody>
      </table>
    </div>
  );
}

function GridView({ documents, empty }: { documents: Document[]; empty?: boolean }) {
  const { t } = useTranslation();
  if (empty) {
    return (
      <p className="rounded-lg border border-slate-200 bg-white py-12 text-center text-slate-400">
        {t('documents.empty')}
      </p>
    );
  }
  return (
    <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5">
      {documents.map((doc) => (
        <Link
          key={doc.id}
          to={`/documents/${doc.id}`}
          className="group overflow-hidden rounded-lg border border-slate-200 bg-white transition-shadow hover:shadow-md"
        >
          <DocumentThumbnail document={doc} />
          <div className="space-y-1 p-3">
            <p
              className="truncate text-sm font-medium text-slate-800 group-hover:text-blue-700"
              title={doc.original_filename}
            >
              {doc.original_filename}
            </p>
            <div className="flex items-center justify-between">
              <StatusBadge status={doc.status} />
              <span className="text-xs text-slate-400">
                {new Date(doc.created_at).toLocaleDateString()}
              </span>
            </div>
          </div>
        </Link>
      ))}
    </div>
  );
}
