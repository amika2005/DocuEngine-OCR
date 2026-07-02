import { useCallback, useRef, useState } from 'react';
import { Link } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { api } from '../../api/client';
import type { DocumentList } from '../../api/types';
import { useEvents } from '../../api/useEvents';
import StatusBadge from '../../components/StatusBadge';

export default function DocumentsPage() {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const [page, setPage] = useState(1);
  const [search, setSearch] = useState('');
  const fileInput = useRef<HTMLInputElement>(null);
  const [uploading, setUploading] = useState(false);

  const { data } = useQuery({
    queryKey: ['documents', page, search],
    queryFn: () =>
      api<DocumentList>(
        `/documents?page=${page}&page_size=25${search ? `&q=${encodeURIComponent(search)}` : ''}`,
      ),
  });

  const refresh = useCallback(
    () => queryClient.invalidateQueries({ queryKey: ['documents'] }),
    [queryClient],
  );
  useEvents('document.', refresh);

  async function onUpload(files: FileList | null) {
    if (!files?.length) return;
    setUploading(true);
    try {
      for (const file of Array.from(files)) {
        const form = new FormData();
        form.append('file', file);
        await api('/documents', { method: 'POST', body: form }).catch((error) => {
          if (error.status !== 409) throw error; // duplicates are fine
        });
      }
      refresh();
    } finally {
      setUploading(false);
      if (fileInput.current) fileInput.current.value = '';
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
        <input
          ref={fileInput}
          type="file"
          multiple
          accept=".pdf,.png,.jpg,.jpeg,.tif,.tiff"
          className="hidden"
          onChange={(event) => onUpload(event.target.files)}
        />
        <button
          onClick={() => fileInput.current?.click()}
          disabled={uploading}
          className="rounded bg-slate-900 px-4 py-1.5 text-sm text-white hover:bg-slate-700 disabled:opacity-50"
        >
          {t('documents.upload')}
        </button>
      </div>

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
            {data?.items.map((doc) => (
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
            {data && data.items.length === 0 && (
              <tr>
                <td colSpan={4} className="px-4 py-8 text-center text-slate-400">
                  {t('documents.empty')}
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

      {totalPages > 1 && (
        <div className="mt-3 flex justify-center gap-2 text-sm">
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
