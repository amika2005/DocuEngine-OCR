import { useCallback, useState } from 'react';
import { Trash2, FileSpreadsheet, Lock } from 'lucide-react';
import { Link } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { api, downloadFile } from '../../api/client';
import type { Document, DocumentList } from '../../api/types';
import { useEvents } from '../../api/useEvents';
import StatusBadge from '../../components/StatusBadge';
import DocumentThumbnail from '../../components/DocumentThumbnail';

type ViewMode = 'list' | 'grid';

const CATEGORIES = [
  'delivery_note',
  'invoice',
  'quotation',
  'receipt',
  'order',
  'tax_report',
  'letter',
  'other',
] as const;

export default function DocumentsPage() {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const [page, setPage] = useState(1);
  const [search, setSearch] = useState('');
  const [docType, setDocType] = useState('');
  const [dateFrom, setDateFrom] = useState('');
  const [dateTo, setDateTo] = useState('');
  const [mineOnly, setMineOnly] = useState(false);
  const [view, setView] = useState<ViewMode>(
    (localStorage.getItem('docuengine-view') as ViewMode) ?? 'list',
  );

  const params = new URLSearchParams({ page: String(page), page_size: '24' });
  if (search) params.set('q', search);
  if (docType) params.set('doc_type', docType);
  if (dateFrom) params.set('created_from', dateFrom);
  if (dateTo) params.set('created_to', dateTo);
  if (mineOnly) params.set('mine', 'true');
  const query = params.toString();

  const { data } = useQuery({
    queryKey: ['documents', query],
    queryFn: () => api<DocumentList>(`/documents?${query}`),
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

  const [reclassifyBusy, setReclassifyBusy] = useState(false);
  async function reclassify() {
    setReclassifyBusy(true);
    try {
      const r = await api<{ updated: number }>(`/documents/reclassify`, { method: 'POST' });
      refresh();
      alert(t('documents.reclassifyDone', { count: r.updated }));
    } finally {
      setReclassifyBusy(false);
    }
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

      {/* Filter bar: category + date range */}
      <div className="mb-4 flex flex-wrap items-center gap-2 text-sm">
        <select
          value={docType}
          onChange={(event) => {
            setDocType(event.target.value);
            setPage(1);
          }}
          className="rounded border border-slate-300 px-2 py-1.5"
        >
          <option value="">{t('documents.allCategories')}</option>
          {CATEGORIES.map((category) => (
            <option key={category} value={category}>
              {t(`documents.categories.${category}`, category)}
            </option>
          ))}
        </select>
        <button
          onClick={reclassify}
          disabled={reclassifyBusy}
          title={t('documents.reclassifyHint')}
          className="rounded border border-slate-300 px-2 py-1.5 text-slate-600 hover:bg-slate-50 disabled:opacity-50"
        >
          {reclassifyBusy ? '…' : t('documents.reclassify')}
        </button>
        <span className="text-slate-400">{t('documents.dateRange')}</span>
        <input
          type="date"
          value={dateFrom}
          onChange={(event) => {
            setDateFrom(event.target.value);
            setPage(1);
          }}
          className="rounded border border-slate-300 px-2 py-1.5"
        />
        <span className="text-slate-400">〜</span>
        <input
          type="date"
          value={dateTo}
          onChange={(event) => {
            setDateTo(event.target.value);
            setPage(1);
          }}
          className="rounded border border-slate-300 px-2 py-1.5"
        />
        <label className="flex cursor-pointer select-none items-center gap-1.5 text-slate-600">
          <input
            type="checkbox"
            checked={mineOnly}
            onChange={(event) => {
              setMineOnly(event.target.checked);
              setPage(1);
            }}
            className="accent-sky-600"
          />
          {t('documents.mineOnly')}
        </label>
        {(docType || dateFrom || dateTo || mineOnly) && (
          <button
            onClick={() => {
              setDocType('');
              setDateFrom('');
              setDateTo('');
              setMineOnly(false);
              setPage(1);
            }}
            className="rounded border border-slate-300 px-2 py-1.5 text-slate-600 hover:bg-slate-50"
          >
            {t('documents.clearFilters')}
          </button>
        )}
        {data && (
          <span className="ml-auto text-xs text-slate-400">
            {t('documents.resultCount', { count: data.total })}
          </span>
        )}
        <button
          onClick={() => {
            const p = new URLSearchParams();
            if (docType) p.set('doc_type', docType);
            if (dateFrom) p.set('created_from', dateFrom);
            if (dateTo) p.set('created_to', dateTo);
            if (search) p.set('q', search);
            downloadFile(`/documents/export/bulk-xlsx?${p.toString()}`, 'documents.xlsx');
          }}
          className={`flex items-center gap-1.5 rounded bg-emerald-700 px-3 py-1.5 text-white hover:bg-emerald-600 ${data ? '' : 'ml-auto'}`}
        >
          <FileSpreadsheet size={15} />
          {t('documents.exportExcel')}
        </button>
      </div>

      {view === 'list' ? (
        <ListView documents={data?.items ?? []} empty={data?.items.length === 0} onDelete={refresh} />
      ) : (
        <GridView documents={data?.items ?? []} empty={data?.items.length === 0} onDelete={refresh} />
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

function ListView({ documents, empty, onDelete }: { documents: Document[]; empty?: boolean; onDelete: () => void }) {
  const { t } = useTranslation();

  async function handleDelete(id: string) {
    if (!confirm(t('common.confirmDelete') || 'Are you sure you want to delete this document?')) return;
    try {
      await api(`/documents/${id}`, { method: 'DELETE' });
      onDelete();
    } catch (e) {
      alert('Failed to delete document');
    }
  }
  return (
    <div className="overflow-hidden rounded-lg border border-slate-200 bg-white">
      <table className="w-full text-sm">
        <thead className="bg-slate-100 text-left text-slate-600">
          <tr>
            <th className="px-4 py-2">{t('documents.filename')}</th>
            <th className="px-4 py-2">{t('documents.category')}</th>
            <th className="px-4 py-2">{t('documents.status')}</th>
            <th className="px-4 py-2">{t('documents.pages')}</th>
            <th className="px-4 py-2">{t('documents.date')}</th>
            <th className="px-4 py-2 text-right">Actions</th>
          </tr>
        </thead>
        <tbody>
          {documents.map((doc) => (
            <tr key={doc.id} className="border-t border-slate-100 hover:bg-slate-50">
              <td className="px-4 py-2">
                <Link to={`/documents/${doc.id}`} className="inline-flex items-center gap-1.5 text-blue-700 hover:underline">
                  {doc.visibility === 'private' && (
                    <Lock size={12} className="shrink-0 text-slate-400" aria-label="private" />
                  )}
                  {doc.original_filename}
                </Link>
              </td>
              <td className="px-4 py-2">
                {doc.doc_type && doc.doc_type !== 'other' ? (
                  <span className="rounded bg-slate-100 px-2 py-0.5 text-xs text-slate-600">
                    {t(`documents.categories.${doc.doc_type}`, doc.doc_type)}
                  </span>
                ) : (
                  <span className="text-slate-300">—</span>
                )}
              </td>
              <td className="px-4 py-2">
                <StatusBadge status={doc.status} />
              </td>
              <td className="px-4 py-2">{doc.page_count || '—'}</td>
              <td className="px-4 py-2">{new Date(doc.created_at).toLocaleString()}</td>
              <td className="px-4 py-2 text-right">
                <button
                  onClick={() => handleDelete(doc.id)}
                  className="rounded p-1 text-red-500 hover:bg-red-50 hover:text-red-700"
                  title="Delete"
                >
                  <Trash2 size={16} />
                </button>
              </td>
            </tr>
          ))}
          {empty && (
            <tr>
              <td colSpan={6} className="px-4 py-8 text-center text-slate-400">
                {t('documents.empty')}
              </td>
            </tr>
          )}
        </tbody>
      </table>
    </div>
  );
}

function GridView({ documents, empty, onDelete }: { documents: Document[]; empty?: boolean; onDelete: () => void }) {
  const { t } = useTranslation();

  async function handleDelete(event: React.MouseEvent, id: string) {
    event.preventDefault(); // Prevent navigating to document detail
    if (!confirm(t('common.confirmDelete') || 'Are you sure you want to delete this document?')) return;
    try {
      await api(`/documents/${id}`, { method: 'DELETE' });
      onDelete();
    } catch (e) {
      alert('Failed to delete document');
    }
  }

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
              <div className="flex items-center gap-2">
                <span className="text-xs text-slate-400">
                  {new Date(doc.created_at).toLocaleDateString()}
                </span>
                <button
                  onClick={(e) => handleDelete(e, doc.id)}
                  className="rounded p-1 text-slate-300 hover:bg-red-50 hover:text-red-600"
                  title="Delete"
                >
                  <Trash2 size={14} />
                </button>
              </div>
            </div>
          </div>
        </Link>
      ))}
    </div>
  );
}
