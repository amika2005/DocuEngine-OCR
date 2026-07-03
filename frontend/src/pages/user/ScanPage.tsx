import { useCallback, useRef, useState, type DragEvent } from 'react';
import { Link } from 'react-router-dom';
import { Upload } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { api, ApiError } from '../../api/client';
import type { Document } from '../../api/types';
import { useEvents } from '../../api/useEvents';
import StatusBadge from '../../components/StatusBadge';

interface ScanItem {
  key: string;
  filename: string;
  state: 'uploading' | 'duplicate' | 'error' | 'tracked';
  error?: string;
  document?: Document;
  progress?: { done: number; total: number };
}

export default function ScanPage() {
  const { t } = useTranslation();
  const [items, setItems] = useState<ScanItem[]>([]);
  const [dragOver, setDragOver] = useState(false);
  const fileInput = useRef<HTMLInputElement>(null);

  const patch = useCallback((key: string, update: Partial<ScanItem>) => {
    setItems((current) =>
      current.map((item) => (item.key === key ? { ...item, ...update } : item)),
    );
  }, []);

  // Live processing status for every document uploaded from this page.
  const onEvent = useCallback(
    (event: { topic: string; data: Record<string, unknown> }) => {
      setItems((current) =>
        current.map((item) => {
          if (!item.document || !event.topic.startsWith(`document.${item.document.id}.`)) {
            return item;
          }
          if (event.topic.endsWith('.progress')) {
            return {
              ...item,
              progress: {
                done: Number(event.data.pages_done ?? 0),
                total: Number(event.data.pages_total ?? 0),
              },
            };
          }
          return {
            ...item,
            document: { ...item.document, status: String(event.data.status ?? item.document.status) },
          };
        }),
      );
    },
    [],
  );
  useEvents('document.', onEvent);

  async function uploadFiles(files: FileList | File[]) {
    for (const file of Array.from(files)) {
      const key = `${file.name}-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
      setItems((current) => [
        { key, filename: file.name, state: 'uploading' },
        ...current,
      ]);
      const form = new FormData();
      form.append('file', file);
      try {
        const document = await api<Document>('/documents', { method: 'POST', body: form });
        patch(key, { state: 'tracked', document });
      } catch (error) {
        if (error instanceof ApiError && error.status === 409) {
          patch(key, { state: 'duplicate' });
        } else {
          patch(key, { state: 'error', error: String((error as Error).message) });
        }
      }
    }
  }

  function onDrop(event: DragEvent) {
    event.preventDefault();
    setDragOver(false);
    if (event.dataTransfer.files.length) void uploadFiles(event.dataTransfer.files);
  }

  return (
    <div>
      <h1 className="mb-1 text-xl font-bold">{t('scan.title')}</h1>
      <p className="mb-4 text-sm text-slate-500">{t('scan.subtitle')}</p>

      <div
        onDragOver={(event) => {
          event.preventDefault();
          setDragOver(true);
        }}
        onDragLeave={() => setDragOver(false)}
        onDrop={onDrop}
        onClick={() => fileInput.current?.click()}
        className={`mb-6 flex cursor-pointer flex-col items-center justify-center rounded-xl border-2 border-dashed py-14 transition-colors ${
          dragOver
            ? 'border-blue-500 bg-blue-50'
            : 'border-slate-300 bg-white hover:border-slate-400'
        }`}
      >
        <Upload className="mb-3 h-10 w-10 text-slate-400" strokeWidth={1.5} aria-hidden />
        <p className="font-medium text-slate-700">{t('scan.dropHere')}</p>
        <p className="mt-1 text-xs text-slate-400">{t('scan.formats')}</p>
        <input
          ref={fileInput}
          type="file"
          multiple
          accept=".pdf,.png,.jpg,.jpeg,.tif,.tiff"
          className="hidden"
          onChange={(event) => {
            if (event.target.files?.length) void uploadFiles(event.target.files);
            event.target.value = '';
          }}
        />
      </div>

      {items.length > 0 && (
        <div className="overflow-hidden rounded-lg border border-slate-200 bg-white">
          <table className="w-full text-sm">
            <thead className="bg-slate-100 text-left text-slate-600">
              <tr>
                <th className="px-4 py-2">{t('documents.filename')}</th>
                <th className="px-4 py-2">{t('documents.status')}</th>
                <th className="px-4 py-2 text-right">{t('scan.result')}</th>
              </tr>
            </thead>
            <tbody>
              {items.map((item) => (
                <tr key={item.key} className="border-t border-slate-100">
                  <td className="px-4 py-2">{item.filename}</td>
                  <td className="px-4 py-2">
                    {item.state === 'uploading' && (
                      <span className="text-blue-600">{t('scan.uploading')}</span>
                    )}
                    {item.state === 'duplicate' && (
                      <span className="text-slate-500">{t('scan.duplicate')}</span>
                    )}
                    {item.state === 'error' && (
                      <span className="text-red-600" title={item.error}>
                        {t('scan.error')}
                      </span>
                    )}
                    {item.state === 'tracked' && item.document && (
                      <span className="flex items-center gap-2">
                        <StatusBadge status={item.document.status} />
                        {item.progress && item.progress.total > 0 && (
                          <span className="text-xs text-slate-500">
                            {item.progress.done}/{item.progress.total}
                          </span>
                        )}
                      </span>
                    )}
                  </td>
                  <td className="px-4 py-2 text-right">
                    {item.document && (
                      <Link
                        to={`/documents/${item.document.id}`}
                        className="text-xs text-blue-700 hover:underline"
                      >
                        {t('scan.open')}
                      </Link>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
