import { useState, type FormEvent } from 'react';
import { useTranslation } from 'react-i18next';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { api, ApiError } from '../../api/client';
import { useLiveInvalidate } from '../../api/useEvents';
import MasterImportWizard from '../../components/MasterImportWizard';
import type { MasterField, MasterRecord, MasterRecordList, MasterType } from '../../api/types';

const EMPTY_FIELD: MasterField = { key: '', label: '', matchable: true, required: false };

export default function MastersPage() {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const [selectedTypeId, setSelectedTypeId] = useState<string | null>(null);
  const [showTypeForm, setShowTypeForm] = useState(false);
  const [importFor, setImportFor] = useState<string | 'ask' | null>(null);
  const [error, setError] = useState('');

  const { data: types } = useQuery({
    queryKey: ['master-types'],
    queryFn: () => api<MasterType[]>('/masters/types'),
  });
  useLiveInvalidate('masters.', [['master-types'], ['master-records']]);

  const selected = types?.find((type) => type.id === selectedTypeId) ?? types?.[0] ?? null;

  async function deleteType(type: MasterType) {
    if (!confirm(t('masters.confirmDeleteType', { name: type.name }))) return;
    await api(`/masters/types/${type.id}`, { method: 'DELETE' });
    queryClient.invalidateQueries({ queryKey: ['master-types'] });
  }

  return (
    <div>
      <div className="mb-4 flex items-center gap-2">
        <h1 className="text-xl font-bold">{t('masters.title')}</h1>
        <button
          onClick={() => setImportFor('ask')}
          className="ml-auto rounded border border-slate-300 bg-white px-4 py-1.5 text-sm hover:bg-slate-50"
        >
          {t('masters.importCsv')}
        </button>
        <button
          onClick={() => setShowTypeForm((value) => !value)}
          className="rounded bg-slate-900 px-4 py-1.5 text-sm text-white hover:bg-slate-700"
        >
          {t('masters.addType')}
        </button>
      </div>

      {error && <p className="mb-3 rounded bg-red-50 p-2 text-sm text-red-700">{error}</p>}
      {showTypeForm && (
        <TypeForm
          onDone={() => {
            setShowTypeForm(false);
            setError('');
            queryClient.invalidateQueries({ queryKey: ['master-types'] });
          }}
          onError={setError}
        />
      )}

      <div className="flex gap-4">
        <aside className="w-56 shrink-0 space-y-1">
          {types?.map((type) => (
            <button
              key={type.id}
              onClick={() => setSelectedTypeId(type.id)}
              className={`flex w-full items-center justify-between rounded-md px-3 py-2 text-left text-sm ${
                selected?.id === type.id
                  ? 'bg-slate-900 text-white'
                  : 'bg-white text-slate-700 hover:bg-slate-100'
              }`}
            >
              <span className="truncate">{type.name}</span>
              <span
                className={`ml-2 rounded-full px-1.5 text-xs ${
                  selected?.id === type.id ? 'bg-slate-700' : 'bg-slate-100 text-slate-500'
                }`}
              >
                {type.records_count}
              </span>
            </button>
          ))}
          {types?.length === 0 && (
            <p className="rounded-md bg-white p-4 text-center text-xs text-slate-400">
              {t('masters.noTypes')}
            </p>
          )}
        </aside>

        <div className="min-w-0 flex-1">
          {selected && (
            <RecordsPanel
              type={selected}
              onDeleteType={() => deleteType(selected)}
              onImport={() => setImportFor(selected.id)}
            />
          )}
        </div>
      </div>

      {importFor && (
        <MasterImportWizard
          types={types ?? []}
          initialTypeId={importFor === 'ask' ? null : importFor}
          onDone={() => {
            queryClient.invalidateQueries({ queryKey: ['master-records'] });
            queryClient.invalidateQueries({ queryKey: ['master-types'] });
          }}
          onClose={() => setImportFor(null)}
        />
      )}
    </div>
  );
}

function TypeForm({ onDone, onError }: { onDone: () => void; onError: (msg: string) => void }) {
  const { t } = useTranslation();
  const [name, setName] = useState('');
  // Starting with no fields is fine — the first bulk import derives the
  // columns from the file's header row.
  const [fields, setFields] = useState<MasterField[]>([]);

  function patchField(index: number, update: Partial<MasterField>) {
    setFields((current) =>
      current.map((field, i) => (i === index ? { ...field, ...update } : field)),
    );
  }

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    try {
      await api('/masters/types', { method: 'POST', body: JSON.stringify({ name, fields }) });
      onDone();
    } catch (error) {
      onError(String((error as ApiError).message));
    }
  }

  return (
    <form onSubmit={onSubmit} className="mb-4 rounded-lg border border-slate-200 bg-white p-4 text-sm">
      <div className="mb-3 flex items-center gap-2">
        <input
          required
          placeholder={t('masters.typeName')}
          value={name}
          onChange={(event) => setName(event.target.value)}
          className="w-64 rounded border border-slate-300 px-3 py-1.5"
        />
        <button
          type="button"
          onClick={() => setFields((current) => [...current, { ...EMPTY_FIELD }])}
          className="rounded border border-slate-300 px-3 py-1.5 text-xs hover:bg-slate-50"
        >
          + {t('masters.addField')}
        </button>
        <button type="submit" className="ml-auto rounded bg-slate-900 px-4 py-1.5 text-white hover:bg-slate-700">
          {t('common.create')}
        </button>
      </div>
      <div className="space-y-2">
        {fields.map((field, index) => (
          <div key={index} className="flex items-center gap-2">
            <input
              required
              placeholder="key (e.g. name)"
              pattern="[a-zA-Z0-9_]+"
              value={field.key}
              onChange={(event) => patchField(index, { key: event.target.value })}
              className="w-40 rounded border border-slate-300 px-2 py-1 font-mono text-xs"
            />
            <input
              required
              placeholder={t('masters.fieldLabel')}
              value={field.label}
              onChange={(event) => patchField(index, { label: event.target.value })}
              className="w-48 rounded border border-slate-300 px-2 py-1"
            />
            <label className="flex items-center gap-1 text-xs text-slate-600">
              <input
                type="checkbox"
                checked={field.matchable}
                onChange={(event) => patchField(index, { matchable: event.target.checked })}
              />
              {t('masters.matchable')}
            </label>
            <label className="flex items-center gap-1 text-xs text-slate-600">
              <input
                type="checkbox"
                checked={field.required}
                onChange={(event) => patchField(index, { required: event.target.checked })}
              />
              {t('masters.required')}
            </label>
            <button
              type="button"
              onClick={() => setFields((current) => current.filter((_, i) => i !== index))}
              className="text-xs text-red-600 hover:underline"
            >
              {t('common.delete')}
            </button>
          </div>
        ))}
      </div>
      <p className="mt-2 text-xs text-slate-400">
        {fields.length === 0 ? t('masters.noFieldsHint') : t('masters.matchableHint')}
      </p>
    </form>
  );
}

function RecordsPanel({
  type,
  onDeleteType,
  onImport,
}: {
  type: MasterType;
  onDeleteType: () => void;
  onImport: () => void;
}) {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const [search, setSearch] = useState('');
  const [page, setPage] = useState(1);
  const [editing, setEditing] = useState<MasterRecord | 'new' | null>(null);

  const { data } = useQuery({
    queryKey: ['master-records', type.id, page, search],
    queryFn: () =>
      api<MasterRecordList>(
        `/masters/types/${type.id}/records?page=${page}${search ? `&q=${encodeURIComponent(search)}` : ''}`,
      ),
  });

  function refresh() {
    queryClient.invalidateQueries({ queryKey: ['master-records'] });
    queryClient.invalidateQueries({ queryKey: ['master-types'] });
  }

  async function deleteRecord(record: MasterRecord) {
    if (!confirm(t('masters.confirmDeleteRecord'))) return;
    await api(`/masters/records/${record.id}`, { method: 'DELETE' });
    refresh();
  }

  const totalPages = data ? Math.max(1, Math.ceil(data.total / data.page_size)) : 1;

  return (
    <div className="rounded-lg border border-slate-200 bg-white">
      <div className="flex items-center gap-2 border-b border-slate-100 p-3">
        <h2 className="font-medium">{type.name}</h2>
        <input
          placeholder={t('masters.searchRecords')}
          value={search}
          onChange={(event) => {
            setSearch(event.target.value);
            setPage(1);
          }}
          className="ml-auto w-56 rounded border border-slate-300 px-3 py-1.5 text-sm"
        />
        <button
          onClick={onImport}
          className="rounded border border-slate-300 px-3 py-1.5 text-sm hover:bg-slate-50"
        >
          {t('masters.importCsv')}
        </button>
        <button
          onClick={() => setEditing('new')}
          disabled={type.fields.length === 0}
          title={type.fields.length === 0 ? t('masters.noFieldsHint') : undefined}
          className="rounded bg-slate-900 px-3 py-1.5 text-sm text-white hover:bg-slate-700 disabled:cursor-not-allowed disabled:opacity-40"
        >
          {t('masters.addRecord')}
        </button>
        <button onClick={onDeleteType} className="px-2 text-xs text-red-600 hover:underline">
          {t('common.delete')}
        </button>
      </div>

      {editing && (
        <RecordForm
          type={type}
          record={editing === 'new' ? null : editing}
          onDone={() => {
            setEditing(null);
            refresh();
          }}
          onCancel={() => setEditing(null)}
        />
      )}

      <table className="w-full text-sm">
        <thead className="bg-slate-50 text-left text-slate-600">
          <tr>
            {type.fields.map((field) => (
              <th key={field.key} className="px-3 py-2">
                {field.label}
                {field.matchable && <span className="ml-1 text-green-600" title={t('masters.matchable')}>✓</span>}
              </th>
            ))}
            <th className="w-24 px-3 py-2" />
          </tr>
        </thead>
        <tbody>
          {data?.items.map((record) => (
            <tr key={record.id} className="border-t border-slate-100 hover:bg-slate-50">
              {type.fields.map((field) => (
                <td key={field.key} className="px-3 py-2">
                  {record.data[field.key] || '—'}
                </td>
              ))}
              <td className="px-3 py-2 text-right text-xs">
                <button onClick={() => setEditing(record)} className="mr-2 text-blue-700 hover:underline">
                  {t('masters.edit')}
                </button>
                <button onClick={() => deleteRecord(record)} className="text-red-600 hover:underline">
                  {t('common.delete')}
                </button>
              </td>
            </tr>
          ))}
          {data?.items.length === 0 && (
            <tr>
              <td colSpan={type.fields.length + 1} className="px-3 py-8 text-center text-slate-400">
                {type.fields.length === 0 ? t('masters.noFieldsHint') : t('masters.noRecords')}
              </td>
            </tr>
          )}
        </tbody>
      </table>

      {totalPages > 1 && (
        <div className="flex justify-center gap-2 border-t border-slate-100 p-2 text-sm">
          {Array.from({ length: totalPages }, (_, index) => index + 1).map((p) => (
            <button
              key={p}
              onClick={() => setPage(p)}
              className={`rounded px-2.5 py-0.5 ${p === page ? 'bg-slate-900 text-white' : 'hover:bg-slate-100'}`}
            >
              {p}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

function RecordForm({
  type,
  record,
  onDone,
  onCancel,
}: {
  type: MasterType;
  record: MasterRecord | null;
  onDone: () => void;
  onCancel: () => void;
}) {
  const { t } = useTranslation();
  const [data, setData] = useState<Record<string, string>>(record?.data ?? {});
  const [error, setError] = useState('');

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    try {
      if (record) {
        await api(`/masters/records/${record.id}`, {
          method: 'PATCH',
          body: JSON.stringify({ data }),
        });
      } else {
        await api(`/masters/types/${type.id}/records`, {
          method: 'POST',
          body: JSON.stringify({ data }),
        });
      }
      onDone();
    } catch (err) {
      setError(String((err as ApiError).message));
    }
  }

  return (
    <form onSubmit={onSubmit} className="border-b border-slate-100 bg-slate-50 p-3 text-sm">
      <div className="grid grid-cols-3 gap-2">
        {type.fields.map((field) => (
          <label key={field.key} className="block">
            <span className="mb-0.5 block text-xs text-slate-500">
              {field.label}
              {field.required && <span className="text-red-500"> *</span>}
            </span>
            <input
              required={field.required}
              value={data[field.key] ?? ''}
              onChange={(event) => setData({ ...data, [field.key]: event.target.value })}
              className="w-full rounded border border-slate-300 px-2 py-1"
            />
          </label>
        ))}
      </div>
      {error && <p className="mt-2 text-xs text-red-600">{error}</p>}
      <div className="mt-2 flex gap-2">
        <button type="submit" className="rounded bg-slate-900 px-4 py-1 text-white hover:bg-slate-700">
          {record ? t('masters.save') : t('common.create')}
        </button>
        <button type="button" onClick={onCancel} className="rounded border border-slate-300 px-4 py-1 hover:bg-white">
          {t('common.cancel')}
        </button>
      </div>
    </form>
  );
}
