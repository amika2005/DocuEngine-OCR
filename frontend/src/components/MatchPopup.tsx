import { useEffect, useRef } from 'react';
import { useTranslation } from 'react-i18next';
import type { MasterMatch } from '../api/types';

/** Popover shown when a highlighted match is clicked: banner with the match
 *  verdict, the OCR→master correction, and the full master record. Linking
 *  replaces the OCR text with the trusted master value. */
export default function MatchPopup({
  match,
  anchor,
  onLink,
  onDismiss,
  onClose,
  busy,
}: {
  match: MasterMatch;
  anchor: HTMLElement;
  onLink: () => void;
  onDismiss: () => void;
  onClose: () => void;
  busy: boolean;
}) {
  const { t } = useTranslation();
  const popupRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    function onClickOutside(event: MouseEvent) {
      if (
        popupRef.current &&
        !popupRef.current.contains(event.target as Node) &&
        !anchor.contains(event.target as Node)
      ) {
        onClose();
      }
    }
    document.addEventListener('mousedown', onClickOutside);
    return () => document.removeEventListener('mousedown', onClickOutside);
  }, [anchor, onClose]);

  const rect = anchor.getBoundingClientRect();
  const linked = match.status === 'linked';
  const exact = match.kind === 'exact' || linked;
  const differs = match.matched_text !== match.master_value;
  // A friendly one-line identity for the record: its first two values.
  const recordSummary = Object.values(match.record_data).filter(Boolean).slice(0, 2).join(' — ');

  return (
    <div
      ref={popupRef}
      className="fixed z-50 w-[26rem] max-w-[95vw] rounded-xl border border-slate-200 bg-white p-4 shadow-2xl"
      style={{
        top: Math.min(rect.bottom + 8, window.innerHeight - 400),
        left: Math.min(rect.left, window.innerWidth - 440),
      }}
    >
      {/* Verdict banner */}
      <div
        className={`mb-3 flex items-center gap-2 rounded-lg px-3 py-2.5 text-sm font-medium ${
          exact
            ? 'bg-emerald-50 text-emerald-800 ring-1 ring-emerald-200'
            : 'bg-amber-50 text-amber-800 ring-1 ring-amber-200'
        }`}
      >
        <svg viewBox="0 0 24 24" className="h-4 w-4 shrink-0" fill="none" stroke="currentColor" strokeWidth="2.5">
          {exact ? (
            <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
          ) : (
            <path strokeLinecap="round" d="M4 12c2-3 4-3 6 0s4 3 6 0" />
          )}
        </svg>
        <span className="min-w-0 truncate">
          {exact ? t('masters.exactMatch') : t('masters.fuzzyMatch')} : {recordSummary}
        </span>
        <span
          className={`ml-auto shrink-0 rounded-full px-2 py-0.5 text-xs tabular-nums ${
            exact ? 'bg-emerald-100' : 'bg-amber-100'
          }`}
        >
          {(match.score * 100).toFixed(0)}%
        </span>
      </div>

      <div className="mb-2 flex items-center gap-2 text-xs text-slate-500">
        <span className="rounded bg-slate-100 px-2 py-0.5 font-medium text-slate-700">
          {match.master_type_name}
        </span>
        <span>
          {t('masters.matchedField')}: <span className="font-medium text-slate-700">{match.field_label}</span>
        </span>
      </div>

      {/* OCR → master correction preview */}
      {differs && (
        <div className="mb-3 rounded-lg bg-slate-50 p-2.5 text-sm">
          <p className="text-xs text-slate-400">{t('masters.ocrText')}</p>
          <p className="text-red-700 line-through">{match.matched_text}</p>
          <p className="mt-1 text-xs text-slate-400">{t('masters.masterValue')}</p>
          <p className="font-medium text-emerald-700">{match.master_value}</p>
        </div>
      )}

      {/* Full master record */}
      <div className="mb-3 overflow-hidden rounded-lg border border-slate-100">
        <table className="w-full text-sm">
          <tbody>
            {Object.entries(match.record_data).map(([key, value]) => (
              <tr key={key} className="border-t border-slate-100 first:border-t-0">
                <td className="w-32 bg-slate-50 px-3 py-1.5 text-xs font-medium text-slate-500">
                  {match.field_labels[key] ?? key}
                </td>
                <td
                  className={`px-3 py-1.5 ${
                    key === match.field_key ? 'font-semibold text-emerald-700' : 'text-slate-800'
                  }`}
                >
                  {value || '—'}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {linked ? (
        <p className="rounded-lg bg-emerald-50 py-2 text-center text-sm font-medium text-emerald-700">
          {t('masters.linked')}
        </p>
      ) : (
        <div className="flex gap-2">
          <button
            onClick={onLink}
            disabled={busy}
            className="flex-1 rounded-lg bg-emerald-600 py-2 text-sm font-medium text-white transition-colors hover:bg-emerald-500 disabled:opacity-50"
          >
            {t('masters.link')}
          </button>
          <button
            onClick={onDismiss}
            disabled={busy}
            className="rounded-lg border border-slate-300 px-4 py-2 text-sm text-slate-600 transition-colors hover:bg-slate-50 disabled:opacity-50"
          >
            {t('masters.dismiss')}
          </button>
        </div>
      )}
    </div>
  );
}
