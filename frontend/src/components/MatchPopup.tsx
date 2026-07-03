import { useEffect, useRef } from 'react';
import { useTranslation } from 'react-i18next';
import type { MasterMatch } from '../api/types';

/** Popover shown when a highlighted match is clicked: the master record's
 *  data with リンク / 却下 actions. Linking replaces the OCR text with the
 *  trusted master value. */
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
  const differs = match.matched_text !== match.master_value;

  return (
    <div
      ref={popupRef}
      className="fixed z-50 w-80 rounded-lg border border-slate-200 bg-white p-4 shadow-xl"
      style={{
        top: Math.min(rect.bottom + 6, window.innerHeight - 320),
        left: Math.min(rect.left, window.innerWidth - 340),
      }}
    >
      <div className="mb-2 flex items-center gap-2">
        <span className="rounded bg-slate-100 px-2 py-0.5 text-xs font-medium">
          {match.master_type_name}
        </span>
        <span className="text-xs text-slate-500">{match.field_label}</span>
        <span className="ml-auto text-xs tabular-nums text-slate-400">
          {(match.score * 100).toFixed(0)}%
        </span>
      </div>

      {differs && (
        <div className="mb-2 rounded bg-slate-50 p-2 text-xs">
          <p className="text-red-700 line-through">{match.matched_text}</p>
          <p className="font-medium text-green-700">→ {match.master_value}</p>
        </div>
      )}

      <table className="mb-3 w-full text-xs">
        <tbody>
          {Object.entries(match.record_data).map(([key, value]) => (
            <tr key={key} className="border-t border-slate-100 first:border-t-0">
              <td className="py-1 pr-2 font-medium text-slate-500">{key}</td>
              <td className={`py-1 ${key === match.field_key ? 'font-medium text-green-700' : ''}`}>
                {value || '—'}
              </td>
            </tr>
          ))}
        </tbody>
      </table>

      {match.status === 'linked' ? (
        <p className="text-center text-xs font-medium text-green-700">
          🔗 {t('masters.linked')}
        </p>
      ) : (
        <div className="flex gap-2">
          <button
            onClick={onLink}
            disabled={busy}
            className="flex-1 rounded bg-green-600 py-1.5 text-sm text-white hover:bg-green-500 disabled:opacity-50"
          >
            🔗 {t('masters.link')}
          </button>
          <button
            onClick={onDismiss}
            disabled={busy}
            className="rounded border border-slate-300 px-3 py-1.5 text-sm text-slate-600 hover:bg-slate-50 disabled:opacity-50"
          >
            {t('masters.dismiss')}
          </button>
        </div>
      )}
    </div>
  );
}
