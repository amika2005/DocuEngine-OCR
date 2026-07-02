import { useTranslation } from 'react-i18next';

const COLORS: Record<string, string> = {
  uploaded: 'bg-slate-100 text-slate-700',
  queued: 'bg-amber-100 text-amber-800',
  processing: 'bg-blue-100 text-blue-800',
  completed: 'bg-green-100 text-green-800',
  failed: 'bg-red-100 text-red-800',
  partially_failed: 'bg-orange-100 text-orange-800',
};

export default function StatusBadge({ status }: { status: string }) {
  const { t } = useTranslation();
  return (
    <span className={`inline-block rounded-full px-2 py-0.5 text-xs ${COLORS[status] ?? 'bg-slate-100'}`}>
      {t(`documents.statusValues.${status}`, status)}
    </span>
  );
}
