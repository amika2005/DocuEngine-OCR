import { useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { api, ApiError } from '../api/client';
import type { MasterType } from '../api/types';

interface Props {
  types: MasterType[];
  initialTypeId?: string | null;
  onDone: () => void; // called after a successful import (refresh lists)
  onClose: () => void;
}

/** Two-step bulk import: first asks WHICH master type the rows belong to
 *  (customers? products? …), then takes a CSV/Excel file for that type. */
interface Preview {
  rows: string[][];
  total_rows: number;
  guessed_header: boolean;
}

export default function MasterImportWizard({ types, initialTypeId, onDone, onClose }: Props) {
  const { t } = useTranslation();
  const [typeId, setTypeId] = useState<string | null>(initialTypeId ?? null);
  const [busy, setBusy] = useState(false);
  const [summary, setSummary] = useState('');
  const [errorLines, setErrorLines] = useState<string[]>([]);
  const [pendingFile, setPendingFile] = useState<File | null>(null);
  const [preview, setPreview] = useState<Preview | null>(null);
  const [hasHeader, setHasHeader] = useState(true);
  const fileInput = useRef<HTMLInputElement>(null);

  const chosen = types.find((type) => type.id === typeId) ?? null;

  function resetFile() {
    setPendingFile(null);
    setPreview(null);
    setSummary('');
    setErrorLines([]);
    if (fileInput.current) fileInput.current.value = '';
  }

  async function loadPreview(files: FileList | null) {
    if (!files?.length || !chosen) return;
    const file = files[0];
    setBusy(true);
    setSummary('');
    setErrorLines([]);
    const form = new FormData();
    form.append('file', file);
    try {
      const result = await api<Preview>(`/masters/types/${chosen.id}/import/preview`, {
        method: 'POST',
        body: form,
      });
      setPendingFile(file);
      setPreview(result);
      setHasHeader(result.guessed_header);
    } catch (error) {
      setSummary(String((error as ApiError).message));
      resetFile();
    } finally {
      setBusy(false);
    }
  }

  async function confirmImport() {
    if (!pendingFile || !chosen) return;
    setBusy(true);
    const form = new FormData();
    form.append('file', pendingFile);
    form.append('has_header', String(hasHeader));
    try {
      const result = await api<{ created: number; skipped: number; errors: string[] }>(
        `/masters/types/${chosen.id}/import`,
        { method: 'POST', body: form },
      );
      setSummary(t('masters.importResult', { created: result.created, skipped: result.skipped }));
      setErrorLines(result.errors);
      setPendingFile(null);
      setPreview(null);
      if (result.created > 0) onDone();
    } catch (error) {
      setSummary(String((error as ApiError).message));
    } finally {
      setBusy(false);
      if (fileInput.current) fileInput.current.value = '';
    }
  }

  function downloadTemplate() {
    if (!chosen) return;
    const header = chosen.fields.map((field) => field.key).join(',');
    const blob = new Blob([`﻿${header}\n`], { type: 'text/csv' });
    const anchor = document.createElement('a');
    anchor.href = URL.createObjectURL(blob);
    anchor.download = `${chosen.name}-template.csv`;
    anchor.click();
    URL.revokeObjectURL(anchor.href);
  }

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/40 p-4"
      onMouseDown={(event) => {
        if (event.target === event.currentTarget) onClose();
      }}
    >
      <div className="w-full max-w-lg rounded-lg bg-white p-5 shadow-xl">
        <div className="mb-4 flex items-center">
          <h2 className="text-lg font-semibold">{t('masters.importTitle')}</h2>
          <button
            onClick={onClose}
            aria-label={t('common.cancel')}
            className="ml-auto rounded p-1 text-slate-400 hover:bg-slate-100 hover:text-slate-600"
          >
            <svg viewBox="0 0 24 24" className="h-5 w-5" fill="none" stroke="currentColor" strokeWidth="2">
              <path strokeLinecap="round" d="M6 6l12 12M18 6L6 18" />
            </svg>
          </button>
        </div>

        {!chosen ? (
          <>
            {/* Step 1 — the "customers or products?" question */}
            <p className="mb-1 font-medium text-slate-800">{t('masters.importWhichType')}</p>
            <p className="mb-3 text-xs text-slate-500">{t('masters.importWhichTypeHint')}</p>
            <div className="space-y-2">
              {types.map((type) => (
                <button
                  key={type.id}
                  onClick={() => setTypeId(type.id)}
                  className="flex w-full cursor-pointer items-center justify-between rounded-md border border-slate-200 px-4 py-3 text-left transition-colors duration-150 hover:border-sky-400 hover:bg-sky-50"
                >
                  <span>
                    <span className="block font-medium text-slate-800">{type.name}</span>
                    <span className="block text-xs text-slate-500">
                      {type.fields.length > 0
                        ? type.fields.map((field) => field.label).join(' · ')
                        : t('masters.noFieldsHint')}
                    </span>
                  </span>
                  <span className="rounded-full bg-slate-100 px-2 py-0.5 text-xs text-slate-500">
                    {type.records_count}
                  </span>
                </button>
              ))}
              {types.length === 0 && (
                <p className="rounded bg-slate-50 p-4 text-center text-sm text-slate-400">
                  {t('masters.noTypes')}
                </p>
              )}
            </div>
          </>
        ) : (
          <>
            {/* Step 2 — file upload for the chosen type */}
            <p className="mb-1 font-medium text-slate-800">
              {t('masters.importRecordsInto', { name: chosen.name })}
            </p>
            <p className="mb-3 text-xs text-slate-500">{t('masters.importFileHint')}</p>
            <input
              ref={fileInput}
              type="file"
              accept=".csv,.xlsx"
              className="hidden"
              onChange={(event) => loadPreview(event.target.files)}
            />
            {!preview ? (
              <div className="flex items-center gap-2">
                <button
                  onClick={() => fileInput.current?.click()}
                  disabled={busy}
                  className="rounded bg-slate-900 px-4 py-2 text-sm text-white hover:bg-slate-700 disabled:opacity-50"
                >
                  {busy ? t('masters.importUploading') : t('masters.importChooseFile')}
                </button>
                {chosen.fields.length > 0 && (
                  <button
                    onClick={downloadTemplate}
                    className="rounded border border-slate-300 px-3 py-2 text-sm hover:bg-slate-50"
                  >
                    {t('masters.csvTemplate')}
                  </button>
                )}
                <button
                  onClick={() => {
                    setTypeId(null);
                    resetFile();
                  }}
                  className="ml-auto text-sm text-slate-500 hover:underline"
                >
                  {t('masters.importBack')}
                </button>
              </div>
            ) : (
              <>
                {/* Preview + "is the first row a header?" confirmation */}
                <div className="mb-3 overflow-x-auto rounded border border-slate-200">
                  <table className="w-full text-xs">
                    <tbody>
                      {preview.rows.map((row, index) => (
                        <tr
                          key={index}
                          className={
                            index === 0 && hasHeader
                              ? 'bg-slate-100 font-medium text-slate-700'
                              : 'border-t border-slate-100'
                          }
                        >
                          <td className="w-8 px-2 py-1 text-right text-slate-400">{index + 1}</td>
                          {row.map((cell, cellIndex) => (
                            <td key={cellIndex} className="px-2 py-1">
                              {cell || '—'}
                            </td>
                          ))}
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
                <label className="mb-3 flex cursor-pointer select-none items-center gap-2 text-sm text-slate-700">
                  <input
                    type="checkbox"
                    checked={hasHeader}
                    onChange={(event) => setHasHeader(event.target.checked)}
                    className="accent-sky-600"
                  />
                  {t('masters.importHasHeader')}
                </label>
                <div className="flex items-center gap-2">
                  <button
                    onClick={confirmImport}
                    disabled={busy}
                    className="rounded bg-slate-900 px-4 py-2 text-sm text-white hover:bg-slate-700 disabled:opacity-50"
                  >
                    {busy
                      ? t('masters.importUploading')
                      : t('masters.importConfirm', {
                          count: preview.total_rows - (hasHeader ? 1 : 0),
                        })}
                  </button>
                  <button
                    onClick={resetFile}
                    className="ml-auto text-sm text-slate-500 hover:underline"
                  >
                    {t('masters.importBack')}
                  </button>
                </div>
              </>
            )}
            {summary && (
              <p className="mt-3 rounded bg-blue-50 px-3 py-2 text-sm text-blue-800">{summary}</p>
            )}
            {errorLines.length > 0 && (
              <ul className="mt-2 max-h-32 space-y-0.5 overflow-y-auto rounded bg-red-50 px-3 py-2 text-xs text-red-700">
                {errorLines.map((line, index) => (
                  <li key={index}>{line}</li>
                ))}
              </ul>
            )}
          </>
        )}
      </div>
    </div>
  );
}
