import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { api } from '../api/client';
import type { ExtractedField, ExtractionResult } from '../api/types';

interface Props {
  documentId: string;
  filename: string;
  extraction: ExtractionResult;
  onChanged: () => void;
  /** Hover sync with the page image: pass the field so the page can highlight
   *  its source region. */
  onFieldHover: (field: ExtractedField | null) => void;
}

/** Extracted template fields as an editable key-value form. Missing required
 *  fields are red, low-confidence values amber; edits save per field. */
export default function FieldsPanel({ documentId, filename, extraction, onChanged, onFieldHover }: Props) {
  const { t } = useTranslation();
  const [drafts, setDrafts] = useState<Record<string, string>>({});
  const [busyKey, setBusyKey] = useState<string | null>(null);

  async function save(field: ExtractedField) {
    const draft = drafts[field.key];
    if (draft === undefined || draft === (field.value ?? '')) return;
    setBusyKey(field.key);
    try {
      await api(`/documents/${documentId}/extracted`, {
        method: 'PATCH',
        body: JSON.stringify({ [field.key]: draft }),
      });
      setDrafts((current) => {
        const next = { ...current };
        delete next[field.key];
        return next;
      });
      onChanged();
    } finally {
      setBusyKey(null);
    }
  }

  function exportCsv() {
    const header = extraction.fields.map((field) => field.label).join(',');
    const row = extraction.fields
      .map((field) => `"${(field.value ?? '').replace(/"/g, '""')}"`)
      .join(',');
    const blob = new Blob([`﻿${header}\n${row}\n`], { type: 'text/csv' });
    const anchor = document.createElement('a');
    anchor.href = URL.createObjectURL(blob);
    anchor.download = `${filename.replace(/\.[^.]+$/, '')}-fields.csv`;
    anchor.click();
    URL.revokeObjectURL(anchor.href);
  }

  return (
    <div>
      <div className="mb-3 flex items-center gap-2">
        <span className="rounded bg-sky-50 px-2 py-0.5 text-xs font-medium text-sky-700">
          {extraction.template_name}
        </span>
        <button
          onClick={exportCsv}
          className="ml-auto rounded border border-slate-300 px-3 py-1 text-xs hover:bg-slate-50"
        >
          {t('templates.exportCsv')}
        </button>
      </div>
      <div className="overflow-hidden rounded-lg border border-slate-200">
        <table className="w-full text-sm">
          <tbody>
            {extraction.fields.map((field) => {
              const draft = drafts[field.key] ?? field.value ?? '';
              const dirty = drafts[field.key] !== undefined && drafts[field.key] !== (field.value ?? '');
              const missing = field.missing && field.required;
              const lowConf = !field.missing && field.confidence < 0.7;
              return (
                <tr
                  key={field.key}
                  onMouseEnter={() => onFieldHover(field)}
                  onMouseLeave={() => onFieldHover(null)}
                  className={`border-t border-slate-100 first:border-t-0 ${
                    missing ? 'bg-red-50' : lowConf ? 'bg-amber-50' : ''
                  }`}
                >
                  <td className="w-40 bg-slate-50 px-3 py-2 align-middle text-xs font-medium text-slate-600">
                    {field.label}
                    {field.required && <span className="text-red-500"> *</span>}
                    <span className="mt-0.5 block font-normal text-slate-400">{t(`templates.types.${field.type}`, field.type)}</span>
                  </td>
                  <td className="px-2 py-1.5">
                    <input
                      value={draft}
                      placeholder={missing ? t('templates.missing') : ''}
                      onChange={(event) =>
                        setDrafts((current) => ({ ...current, [field.key]: event.target.value }))
                      }
                      onBlur={() => save(field)}
                      onKeyDown={(event) => {
                        if (event.key === 'Enter') (event.target as HTMLInputElement).blur();
                      }}
                      className={`w-full rounded border px-2 py-1.5 transition-colors focus:outline-none ${
                        missing
                          ? 'border-red-300 placeholder-red-400'
                          : 'border-transparent hover:border-slate-200'
                      } focus:border-sky-400`}
                    />
                  </td>
                  <td className="w-16 px-2 py-2 text-right align-middle">
                    {busyKey === field.key ? (
                      <span className="text-xs text-slate-400">…</span>
                    ) : dirty ? (
                      <span className="text-xs text-sky-600">↵</span>
                    ) : field.missing ? (
                      <span className="rounded bg-red-100 px-1.5 py-0.5 text-[10px] font-medium text-red-700">
                        {t('templates.missing')}
                      </span>
                    ) : (
                      <span
                        className={`rounded px-1.5 py-0.5 text-[10px] font-medium ${
                          field.confidence >= 0.7
                            ? 'bg-slate-100 text-slate-500'
                            : 'bg-amber-100 text-amber-800'
                        }`}
                        title={t('detail.confidence')}
                      >
                        {Math.round(field.confidence * 100)}%
                      </span>
                    )}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      <p className="mt-2 text-xs text-slate-400">{t('templates.fieldsHint')}</p>
    </div>
  );
}
