import { useState, type FormEvent } from 'react';
import { useTranslation } from 'react-i18next';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { api, ApiError } from '../../api/client';
import { useLiveInvalidate } from '../../api/useEvents';
import type { Template, TemplateField } from '../../api/types';

const EMPTY_FIELD: TemplateField = {
  key: '',
  label: '',
  description: '',
  type: 'text',
  required: false,
};

const DOC_TYPES = ['invoice', 'tax_report', 'quotation', 'letter', 'other'] as const;

export default function TemplatesPage() {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const [editing, setEditing] = useState<Template | 'new' | null>(null);

  const { data: templates } = useQuery({
    queryKey: ['templates'],
    queryFn: () => api<Template[]>('/templates'),
  });
  useLiveInvalidate('templates.', [['templates']]);

  async function deleteTemplate(template: Template) {
    if (!confirm(t('templates.confirmDelete', { name: template.name }))) return;
    await api(`/templates/${template.id}`, { method: 'DELETE' });
    queryClient.invalidateQueries({ queryKey: ['templates'] });
  }

  return (
    <div>
      <div className="mb-4 flex items-center">
        <h1 className="text-xl font-bold">{t('templates.title')}</h1>
        <button
          onClick={() => setEditing('new')}
          className="ml-auto rounded bg-slate-900 px-4 py-1.5 text-sm text-white hover:bg-slate-700"
        >
          + {t('templates.newTemplate')}
        </button>
      </div>

      {editing && (
        <TemplateForm
          template={editing === 'new' ? null : editing}
          onDone={() => {
            setEditing(null);
            queryClient.invalidateQueries({ queryKey: ['templates'] });
          }}
          onCancel={() => setEditing(null)}
        />
      )}

      <div className="space-y-3">
        {templates?.map((template) => (
          <div
            key={template.id}
            className="rounded-lg border border-slate-200 bg-white p-4"
          >
            <div className="flex items-center gap-3">
              <div className="min-w-0 flex-1">
                <div className="flex items-center gap-2">
                  <h2 className="font-semibold">{template.name}</h2>
                  <span className="rounded bg-slate-100 px-2 py-0.5 text-xs text-slate-600">
                    {t(`templates.docTypes.${template.doc_type}`, template.doc_type)}
                  </span>
                  <span className="rounded-full bg-sky-50 px-2 py-0.5 text-xs text-sky-700">
                    {t('templates.docCount', { count: template.documents_count })}
                  </span>
                </div>
                {template.description && (
                  <p className="mt-0.5 text-sm text-slate-500">{template.description}</p>
                )}
              </div>
              <button
                onClick={() => setEditing(template)}
                className="text-sm text-blue-700 hover:underline"
              >
                {t('masters.edit')}
              </button>
              <button
                onClick={() => deleteTemplate(template)}
                className="text-sm text-red-600 hover:underline"
              >
                {t('common.delete')}
              </button>
            </div>
            <div className="mt-2 flex flex-wrap gap-1.5">
              {template.fields.map((field) => (
                <span
                  key={field.key}
                  className="rounded border border-slate-200 bg-slate-50 px-2 py-0.5 text-xs text-slate-600"
                >
                  {field.label}
                  <span className="ml-1 text-slate-400">{field.type}</span>
                  {field.required && <span className="ml-0.5 text-red-500">*</span>}
                </span>
              ))}
            </div>
          </div>
        ))}
        {templates?.length === 0 && !editing && (
          <p className="rounded-lg border border-slate-200 bg-white p-10 text-center text-sm text-slate-400">
            {t('templates.empty')}
          </p>
        )}
      </div>
    </div>
  );
}

function TemplateForm({
  template,
  onDone,
  onCancel,
}: {
  template: Template | null;
  onDone: () => void;
  onCancel: () => void;
}) {
  const { t } = useTranslation();
  const [name, setName] = useState(template?.name ?? '');
  const [docType, setDocType] = useState(template?.doc_type ?? 'invoice');
  const [description, setDescription] = useState(template?.description ?? '');
  const [fields, setFields] = useState<TemplateField[]>(
    template?.fields ?? [{ ...EMPTY_FIELD, required: true }],
  );
  const [error, setError] = useState('');

  function patchField(index: number, update: Partial<TemplateField>) {
    setFields((current) => current.map((f, i) => (i === index ? { ...f, ...update } : f)));
  }

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    const body = JSON.stringify({ name, doc_type: docType, description, fields });
    try {
      if (template) {
        await api(`/templates/${template.id}`, { method: 'PATCH', body });
      } else {
        await api('/templates', { method: 'POST', body });
      }
      onDone();
    } catch (err) {
      setError(String((err as ApiError).message));
    }
  }

  return (
    <form onSubmit={onSubmit} className="mb-4 rounded-lg border border-slate-200 bg-white p-5 text-sm">
      <h2 className="mb-4 text-base font-semibold">
        {template ? t('templates.editTemplate') : t('templates.createTemplate')}
      </h2>
      <div className="mb-3 grid grid-cols-2 gap-3">
        <label className="block">
          <span className="mb-1 block text-xs font-medium text-slate-600">
            {t('templates.name')} <span className="text-red-500">*</span>
          </span>
          <input
            required
            value={name}
            onChange={(event) => setName(event.target.value)}
            placeholder={t('templates.namePlaceholder')}
            className="w-full rounded border border-slate-300 px-3 py-1.5"
          />
        </label>
        <label className="block">
          <span className="mb-1 block text-xs font-medium text-slate-600">{t('templates.docType')}</span>
          <select
            value={docType}
            onChange={(event) => setDocType(event.target.value)}
            className="w-full rounded border border-slate-300 px-3 py-1.5"
          >
            {DOC_TYPES.map((value) => (
              <option key={value} value={value}>
                {t(`templates.docTypes.${value}`, value)}
              </option>
            ))}
          </select>
        </label>
      </div>
      <label className="mb-4 block">
        <span className="mb-1 block text-xs font-medium text-slate-600">{t('templates.description')}</span>
        <input
          value={description}
          onChange={(event) => setDescription(event.target.value)}
          placeholder={t('templates.descriptionPlaceholder')}
          className="w-full rounded border border-slate-300 px-3 py-1.5"
        />
      </label>

      <div className="mb-2 flex items-center">
        <h3 className="font-medium">{t('templates.extractionFields')}</h3>
        <button
          type="button"
          onClick={() => setFields((current) => [...current, { ...EMPTY_FIELD }])}
          className="ml-auto rounded border border-slate-300 px-3 py-1 text-xs hover:bg-slate-50"
        >
          + {t('templates.addField')}
        </button>
      </div>
      <div className="space-y-2">
        {fields.map((field, index) => (
          <div key={index} className="grid grid-cols-[1fr_1.4fr_7rem_auto_auto] items-center gap-2 rounded border border-slate-100 bg-slate-50 p-2">
            <input
              required
              placeholder={t('templates.fieldLabel')}
              value={field.label}
              onChange={(event) => {
                const label = event.target.value;
                // Auto-derive the key from ASCII labels; Japanese labels get field_N.
                const auto = /^[\x00-\x7F]*$/.test(label)
                  ? label.toLowerCase().replace(/[^a-z0-9_]+/g, '_').replace(/^_+|_+$/g, '')
                  : field.key || `field_${index + 1}`;
                patchField(index, { label, key: auto || `field_${index + 1}` });
              }}
              className="rounded border border-slate-300 px-2 py-1.5"
            />
            <input
              placeholder={t('templates.fieldDescription')}
              value={field.description}
              onChange={(event) => patchField(index, { description: event.target.value })}
              className="rounded border border-slate-300 px-2 py-1.5"
            />
            <select
              value={field.type}
              onChange={(event) => patchField(index, { type: event.target.value as TemplateField['type'] })}
              className="rounded border border-slate-300 px-2 py-1.5"
            >
              <option value="text">{t('templates.types.text')}</option>
              <option value="date">{t('templates.types.date')}</option>
              <option value="number">{t('templates.types.number')}</option>
              <option value="amount">{t('templates.types.amount')}</option>
            </select>
            <label className="flex items-center gap-1 text-xs text-slate-600">
              <input
                type="checkbox"
                checked={field.required}
                onChange={(event) => patchField(index, { required: event.target.checked })}
                className="accent-sky-600"
              />
              {t('masters.required')}
            </label>
            <button
              type="button"
              onClick={() => setFields((current) => current.filter((_, i) => i !== index))}
              disabled={fields.length <= 1}
              className="px-1 text-xs text-red-600 hover:underline disabled:opacity-30"
            >
              {t('common.delete')}
            </button>
          </div>
        ))}
      </div>
      <p className="mt-2 text-xs text-slate-400">{t('templates.fieldHint')}</p>

      {error && <p className="mt-2 text-xs text-red-600">{error}</p>}
      <div className="mt-3 flex gap-2">
        <button type="submit" className="rounded bg-slate-900 px-4 py-1.5 text-white hover:bg-slate-700">
          {template ? t('masters.save') : t('common.create')}
        </button>
        <button type="button" onClick={onCancel} className="rounded border border-slate-300 px-4 py-1.5 hover:bg-slate-50">
          {t('common.cancel')}
        </button>
      </div>
    </form>
  );
}
