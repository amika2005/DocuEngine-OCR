import { useCallback, useEffect, useRef, useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { api, ApiError, downloadFile } from '../../api/client';
import type {
  Document,
  DocumentList,
  ExtractedField,
  FieldMatches,
  MasterMatch,
  OcrResult,
  Page,
  Template,
} from '../../api/types';
import { useEvents } from '../../api/useEvents';
import StatusBadge from '../../components/StatusBadge';
import PageViewer from '../../components/PageViewer';
import RegionOverlayViewer from '../../components/RegionOverlayViewer';
import RegionTextPanel from '../../components/RegionTextPanel';
import MatchableMarkdown from '../../components/MatchableMarkdown';
import MatchPopup from '../../components/MatchPopup';
import ResultEditor from '../../components/ResultEditor';
import FieldsPanel from '../../components/FieldsPanel';

type ResultTab = 'fields' | 'markdown' | 'lines' | 'json';

export default function DocumentDetailPage() {
  const { id } = useParams<{ id: string }>();
  const { t } = useTranslation();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [selectedPage, setSelectedPage] = useState(0);
  const [progress, setProgress] = useState<{ done: number; total: number } | null>(null);
  const [popup, setPopup] = useState<{ match: MasterMatch; anchor: HTMLElement } | null>(null);
  const [linkBusy, setLinkBusy] = useState(false);
  const [resultTab, setResultTab] = useState<ResultTab>('markdown');
  const [showBoxes, setShowBoxes] = useState(true);
  const [hoveredRegion, setHoveredRegion] = useState<number | null>(null);
  const [scrollToRegion, setScrollToRegion] = useState<number | null>(null);
  const [editingResult, setEditingResult] = useState(false);
  const [editNonce, setEditNonce] = useState(0); // remounts the editor per session
  const [draft, setDraft] = useState('');
  const [saveBusy, setSaveBusy] = useState(false);
  // Split position (% width of the left pane), draggable via the divider.
  const [split, setSplit] = useState(() => {
    const saved = Number(localStorage.getItem('detail-split'));
    return saved >= 25 && saved <= 75 ? saved : 50;
  });
  const splitContainer = useRef<HTMLDivElement>(null);

  function startSplitDrag(event: React.MouseEvent) {
    event.preventDefault();
    const container = splitContainer.current;
    if (!container) return;
    const onMove = (ev: MouseEvent) => {
      const rect = container.getBoundingClientRect();
      const pct = ((ev.clientX - rect.left) / rect.width) * 100;
      setSplit(Math.min(75, Math.max(25, pct)));
    };
    const onUp = () => {
      window.removeEventListener('mousemove', onMove);
      window.removeEventListener('mouseup', onUp);
      document.body.style.cursor = '';
      setSplit((current) => {
        localStorage.setItem('detail-split', String(Math.round(current)));
        return current;
      });
    };
    document.body.style.cursor = 'col-resize';
    window.addEventListener('mousemove', onMove);
    window.addEventListener('mouseup', onUp);
  }

  const { data: doc } = useQuery({
    queryKey: ['document', id],
    queryFn: () => api<Document>(`/documents/${id}`),
  });
  const { data: pages } = useQuery({
    queryKey: ['document-pages', id],
    queryFn: () => api<Page[]>(`/documents/${id}/pages`),
    enabled: !!doc && doc.status !== 'uploaded',
  });
  const { data: markdown } = useQuery({
    queryKey: ['document-markdown', id],
    queryFn: () => api<string>(`/documents/${id}/markdown`),
    enabled: !!doc && (doc.status === 'completed' || doc.status === 'partially_failed'),
  });

  const currentPage = pages?.[selectedPage];
  const { data: pageResult } = useQuery({
    queryKey: ['page-result', currentPage?.id],
    queryFn: () => api<OcrResult>(`/pages/${currentPage!.id}/result`),
    enabled: !!currentPage && currentPage.status === 'completed',
  });
  const regions = pageResult?.layout_json.regions ?? [];

  // Prev/next navigation across the document list (newest first).
  const { data: docList } = useQuery({
    queryKey: ['documents-nav'],
    queryFn: () => api<DocumentList>('/documents?page_size=100'),
  });
  const { data: templates } = useQuery({
    queryKey: ['templates'],
    queryFn: () => api<Template[]>('/templates'),
  });
  const siblings = docList?.items ?? [];
  const docIndex = siblings.findIndex((item) => item.id === id);
  const prevDoc = docIndex > 0 ? siblings[docIndex - 1] : null;
  const nextDoc = docIndex >= 0 && docIndex < siblings.length - 1 ? siblings[docIndex + 1] : null;

  // Fresh view state when navigating between documents.
  useEffect(() => {
    setSelectedPage(0);
    setProgress(null);
    setHoveredRegion(null);
    setScrollToRegion(null);
    setResultTab('markdown');
    setPopup(null);
    setEditingResult(false);
  }, [id]);

  // Template-extracted documents open on the Fields tab — that's the payoff.
  const hasExtraction = !!doc?.extracted_json;
  useEffect(() => {
    if (hasExtraction) setResultTab('fields');
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id, hasExtraction]);

  async function changeTemplate(templateId: string) {
    const query = templateId ? `?template_id=${templateId}` : '';
    await api(`/documents/${id}/apply-template${query}`, { method: 'POST' });
    invalidateAll();
  }

  // Hovering an extracted field highlights its source region on the scan.
  function onFieldHover(field: ExtractedField | null) {
    if (!field || !field.bbox || field.page_number !== currentPage?.page_number) {
      setHoveredRegion(null);
      return;
    }
    const [x0, y0] = field.bbox;
    const index = regions.findIndex(
      (region) => Math.abs(region.bbox[0] - x0) < 2 && Math.abs(region.bbox[1] - y0) < 2,
    );
    setHoveredRegion(index >= 0 ? index : null);
  }

  function startEditing() {
    setDraft(pageResult?.markdown ?? '');
    setEditNonce((n) => n + 1);
    setEditingResult(true);
  }

  async function saveEdit() {
    if (!currentPage) return;
    setSaveBusy(true);
    try {
      await api(`/pages/${currentPage.id}/corrections`, {
        method: 'POST',
        body: JSON.stringify({ corrected_markdown: draft, apply: true }),
      });
      invalidateAll();
    } catch (err) {
      if (!(err instanceof ApiError && err.status === 422)) throw err;
    } finally {
      setEditingResult(false);
      setSaveBusy(false);
    }
  }

  // Clicking a bbox scrolls the Markdown result to that region's text.
  const markdownRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (scrollToRegion == null || resultTab !== 'markdown') return;
    const container = markdownRef.current;
    const region = regions[scrollToRegion];
    if (!container || !region) return;
    let needle = region.markdown;
    if (region.kind === 'table') {
      const firstRow = needle.split('\n')[0] ?? '';
      needle =
        firstRow
          .split('|')
          .map((cell) => cell.trim())
          .find((cell) => cell && !/^[-\s]+$/.test(cell)) ?? '';
    }
    needle = needle.replace(/\s+/g, ' ').trim().slice(0, 30);
    if (needle) {
      const walker = document.createTreeWalker(container, NodeFilter.SHOW_TEXT);
      let node: Node | null;
      while ((node = walker.nextNode())) {
        if (node.textContent && node.textContent.replace(/\s+/g, ' ').includes(needle)) {
          const el = node.parentElement;
          if (el) {
            el.scrollIntoView({ block: 'center', behavior: 'smooth' });
            el.animate(
              [{ backgroundColor: '#fde68a' }, { backgroundColor: 'transparent' }],
              { duration: 1800 },
            );
          }
          break;
        }
      }
    }
    // Clear so clicking the same box again re-triggers the scroll.
    const timer = setTimeout(() => setScrollToRegion(null), 400);
    return () => clearTimeout(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [scrollToRegion, resultTab]);
  const { data: matches } = useQuery({
    queryKey: ['page-matches', currentPage?.id],
    queryFn: () => api<MasterMatch[]>(`/pages/${currentPage!.id}/matches`),
    enabled: !!currentPage,
  });
  // Per-field master link state for the Fields tab (whole-document, all pages).
  const { data: fieldMatches } = useQuery({
    queryKey: ['document-field-matches', id],
    queryFn: () => api<FieldMatches>(`/documents/${id}/field-matches`),
    enabled: hasExtraction,
  });

  const invalidateAll = useCallback(() => {
    queryClient.invalidateQueries({ queryKey: ['document', id] });
    queryClient.invalidateQueries({ queryKey: ['document-pages', id] });
    queryClient.invalidateQueries({ queryKey: ['document-markdown', id] });
    queryClient.invalidateQueries({ queryKey: ['page-result'] });
    queryClient.invalidateQueries({ queryKey: ['page-matches'] });
    queryClient.invalidateQueries({ queryKey: ['document-field-matches', id] });
  }, [id, queryClient]);

  const onEvent = useCallback(
    (event: { topic: string; data: Record<string, unknown> }) => {
      if (event.topic.endsWith('.progress')) {
        setProgress({
          done: Number(event.data.pages_done ?? 0),
          total: Number(event.data.pages_total ?? 0),
        });
        return;
      }
      if (event.topic.startsWith(`document.${id}.`) || event.topic === 'matches.changed') {
        invalidateAll();
      }
    },
    [id, invalidateAll],
  );
  useEvents([`document.${id}`, 'matches.changed'], onEvent);

  async function actOnMatch(action: 'link' | 'dismiss') {
    if (!popup) return;
    setLinkBusy(true);
    try {
      await api(`/matches/${popup.match.id}/${action}`, { method: 'POST' });
      setPopup(null);
      invalidateAll();
    } finally {
      setLinkBusy(false);
    }
  }

  async function rematch() {
    await api(`/documents/${id}/rematch`, { method: 'POST' });
  }

  async function toggleVisibility() {
    if (!doc) return;
    const next = doc.visibility === 'private' ? 'shared' : 'private';
    await api(`/documents/${id}/visibility?visibility=${next}`, { method: 'PATCH' });
    invalidateAll();
  }

  async function handleDelete() {
    if (!confirm(t('common.confirmDelete') || 'Are you sure you want to delete this document?')) return;
    try {
      await api(`/documents/${id}`, { method: 'DELETE' });
      navigate('/documents');
    } catch (e) {
      alert('Failed to delete document');
    }
  }

  if (!doc) return <p className="text-slate-500">{t('common.loading')}</p>;

  const processing = doc.status === 'queued' || doc.status === 'processing';
  const suggestedCount = matches?.filter((match) => match.status === 'suggested').length ?? 0;
  const filenameStem = doc.original_filename.replace(/\.[^.]+$/, '');

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      {/* Header bar */}
      <div className="mb-3 flex shrink-0 items-center gap-3">
        <div className="flex shrink-0 items-center gap-1">
          <button
            onClick={() => prevDoc && navigate(`/documents/${prevDoc.id}`)}
            disabled={!prevDoc}
            title={prevDoc?.original_filename}
            aria-label="previous document"
            className="rounded border border-slate-300 bg-white p-1.5 text-slate-600 hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-30"
          >
            <svg viewBox="0 0 24 24" className="h-4 w-4" fill="none" stroke="currentColor" strokeWidth="2.5">
              <path strokeLinecap="round" strokeLinejoin="round" d="M15 19l-7-7 7-7" />
            </svg>
          </button>
          <button
            onClick={() => nextDoc && navigate(`/documents/${nextDoc.id}`)}
            disabled={!nextDoc}
            title={nextDoc?.original_filename}
            aria-label="next document"
            className="rounded border border-slate-300 bg-white p-1.5 text-slate-600 hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-30"
          >
            <svg viewBox="0 0 24 24" className="h-4 w-4" fill="none" stroke="currentColor" strokeWidth="2.5">
              <path strokeLinecap="round" strokeLinejoin="round" d="M9 5l7 7-7 7" />
            </svg>
          </button>
        </div>
        <h1 className="min-w-0 flex-1 truncate text-xl font-bold">{doc.original_filename}</h1>
        <button
          onClick={toggleVisibility}
          title={t('detail.visibilityHint')}
          className={`flex shrink-0 items-center gap-1 rounded-full px-2.5 py-0.5 text-xs font-medium transition-colors ${
            doc.visibility === 'private'
              ? 'bg-amber-100 text-amber-800 hover:bg-amber-200'
              : 'bg-sky-100 text-sky-800 hover:bg-sky-200'
          }`}
        >
          {doc.visibility === 'private' ? t('detail.visPrivate') : t('detail.visShared')}
        </button>
        <StatusBadge status={doc.status} />
        {suggestedCount > 0 && (
          <span className="rounded-full bg-green-100 px-2 py-0.5 text-xs text-green-800">
            ✓ {t('masters.matchCount', { count: suggestedCount })}
          </span>
        )}
        <div className="flex shrink-0 gap-2">
          <button
            onClick={rematch}
            className="rounded border border-slate-300 bg-white px-3 py-1.5 text-sm hover:bg-slate-50"
            title={t('masters.rematchHint')}
          >
            {t('masters.rematch')}
          </button>
          {markdown != null && (
            <>
              <button
                onClick={() => downloadFile(`/documents/${doc.id}/export/pdf`, `${filenameStem}.pdf`)}
                className="flex items-center gap-1.5 rounded bg-slate-900 px-3 py-1.5 text-sm text-white hover:bg-slate-700"
              >
                <svg viewBox="0 0 24 24" className="h-3.5 w-3.5" fill="none" stroke="currentColor" strokeWidth="2">
                  <path strokeLinecap="round" strokeLinejoin="round" d="M12 4v12m0 0l-4-4m4 4l4-4M5 20h14" />
                </svg>
                PDF
              </button>
              <button
                onClick={() => downloadFile(`/documents/${doc.id}/export/xlsx`, `${filenameStem}.xlsx`)}
                className="flex items-center gap-1.5 rounded bg-emerald-700 px-3 py-1.5 text-sm text-white hover:bg-emerald-600"
              >
                <svg viewBox="0 0 24 24" className="h-3.5 w-3.5" fill="none" stroke="currentColor" strokeWidth="2">
                  <path strokeLinecap="round" strokeLinejoin="round" d="M12 4v12m0 0l-4-4m4 4l4-4M5 20h14" />
                </svg>
                Excel
              </button>
            </>
          )}
          <button
            onClick={handleDelete}
            className="rounded border border-red-200 bg-red-50 px-3 py-1.5 text-sm text-red-700 hover:bg-red-100"
            title="Delete Document"
          >
            {t('common.delete') || 'Delete'}
          </button>
        </div>
      </div>

      {/* Processing progress */}
      {processing && (
        <div className="mb-3 shrink-0 rounded-lg border border-blue-200 bg-blue-50 p-4">
          <p className="text-sm text-blue-800">
            {progress
              ? t('detail.progress', { done: progress.done, total: progress.total })
              : t('common.loading')}
          </p>
          {progress && progress.total > 0 && (
            <div className="mt-2 h-2 overflow-hidden rounded bg-blue-100">
              <div
                className="h-full bg-blue-600 transition-all"
                style={{ width: `${(progress.done / progress.total) * 100}%` }}
              />
            </div>
          )}
        </div>
      )}

      {/* Error message */}
      {doc.error_message && (
        <p className="mb-3 shrink-0 rounded border border-red-200 bg-red-50 p-3 text-sm text-red-700">
          {doc.error_message}
        </p>
      )}

      {/* Per-page OCR failure reason (why a page failed, not just "failed") */}
      {currentPage?.status === 'failed' && currentPage.error_message && (
        <div className="mb-3 shrink-0 rounded border border-red-200 bg-red-50 p-3 text-sm text-red-700">
          <p className="font-medium">{t('detail.pageFailed', { page: currentPage.page_number })}</p>
          <code className="mt-1 block break-all text-xs">{currentPage.error_message}</code>
        </div>
      )}

      {/* Two-column split — divider drags to resize, position persists */}
      <div ref={splitContainer} className="flex min-h-0 flex-1">
        <section
          style={{ width: `${split}%` }}
          className="flex min-w-0 flex-col overflow-hidden rounded-lg border border-slate-200 bg-white"
        >
          <div className="flex shrink-0 items-center justify-between gap-2 border-b border-slate-100 px-4 py-3">
            <h2 className="font-medium text-slate-700">{t('detail.originalImage')}</h2>
            <div className="flex items-center gap-2">
              {pageResult && (
                <span
                  className="hidden rounded-full bg-slate-100 px-2 py-0.5 text-xs text-slate-600 lg:inline"
                  title={t('detail.confidence')}
                >
                  {pageResult.engine}
                  {pageResult.avg_confidence != null &&
                    ` · ${Math.round(pageResult.avg_confidence * 100)}%`}
                </span>
              )}
              {regions.length > 0 && (
                <label className="flex cursor-pointer select-none items-center gap-1.5 text-sm text-slate-600">
                  <input
                    type="checkbox"
                    checked={showBoxes}
                    onChange={(event) => setShowBoxes(event.target.checked)}
                    className="accent-sky-600"
                  />
                  {t('detail.boxes')}
                </label>
              )}
              {pages && pages.length > 1 && (
                <select
                  value={selectedPage}
                  onChange={(event) => {
                    setSelectedPage(Number(event.target.value));
                    setHoveredRegion(null);
                    setScrollToRegion(null);
                    setEditingResult(false);
                  }}
                  className="rounded border border-slate-300 px-2 py-1 text-sm"
                >
                  {pages.map((page, index) => (
                    <option key={page.id} value={index}>
                      p.{page.page_number}
                    </option>
                  ))}
                </select>
              )}
            </div>
          </div>
          <div className="flex-1 overflow-auto p-3">
            {currentPage && regions.length > 0 ? (
              <RegionOverlayViewer
                path={`/pages/${currentPage.id}/image`}
                pageWidth={currentPage.width_px}
                pageHeight={currentPage.height_px}
                regions={regions}
                hovered={hoveredRegion}
                onHover={setHoveredRegion}
                onSelect={(index) => {
                  // Jump to the region's text in the Markdown result; fall
                  // back to the line list when no markdown exists yet.
                  setResultTab(markdown != null ? 'markdown' : 'lines');
                  setScrollToRegion(index);
                }}
                showBoxes={showBoxes}
              />
            ) : currentPage ? (
              <PageViewer path={`/pages/${currentPage.id}/image`} />
            ) : (
              <p className="py-12 text-center text-slate-400">—</p>
            )}
          </div>
        </section>

        <div
          onMouseDown={startSplitDrag}
          onDoubleClick={() => {
            setSplit(50);
            localStorage.setItem('detail-split', '50');
          }}
          title="drag to resize / double-click to reset"
          className="group flex w-4 shrink-0 cursor-col-resize items-center justify-center"
        >
          <div className="h-16 w-1 rounded-full bg-slate-300 transition-colors duration-150 group-hover:bg-sky-500 group-active:bg-sky-600" />
        </div>

        <section className="flex min-w-0 flex-1 flex-col overflow-hidden rounded-lg border border-slate-200 bg-white">
          <div className="flex shrink-0 items-center gap-1 border-b border-slate-100 px-4 py-2">
            {([...(hasExtraction ? (['fields'] as const) : []), 'markdown', 'lines', 'json'] as const).map(
              (tab) => (
                <button
                  key={tab}
                  onClick={() => {
                    setResultTab(tab);
                    setEditingResult(false);
                  }}
                  className={`rounded px-3 py-1.5 text-sm transition-colors duration-150 ${
                    resultTab === tab
                      ? 'bg-slate-900 text-white'
                      : 'text-slate-600 hover:bg-slate-100'
                  }`}
                >
                  {tab === 'fields'
                    ? t('templates.fieldsTab')
                    : tab === 'markdown'
                      ? t('detail.markdown')
                      : tab === 'lines'
                        ? t('detail.textLines')
                        : 'JSON'}
                </button>
              ),
            )}
            {templates && templates.length > 0 && !editingResult && (
              <select
                value={doc.template_id ?? ''}
                onChange={(event) => void changeTemplate(event.target.value)}
                title={t('scan.template')}
                className={`${resultTab === 'markdown' && pageResult ? '' : 'ml-auto '}rounded border border-slate-200 px-2 py-1 text-xs text-slate-600`}
              >
                <option value="">{t('scan.noTemplate')}</option>
                {templates.map((template) => (
                  <option key={template.id} value={template.id}>
                    {template.name}
                  </option>
                ))}
              </select>
            )}
            {resultTab === 'markdown' && pageResult && !editingResult && (
              <button
                onClick={startEditing}
                className="ml-auto flex items-center gap-1.5 rounded border border-slate-300 px-3 py-1.5 text-sm text-slate-600 transition-colors hover:bg-slate-50"
              >
                <svg viewBox="0 0 24 24" className="h-3.5 w-3.5" fill="none" stroke="currentColor" strokeWidth="2">
                  <path strokeLinecap="round" strokeLinejoin="round" d="M16.5 4.5l3 3L8 19H5v-3L16.5 4.5z" />
                </svg>
                {t('detail.edit')}
              </button>
            )}
            {editingResult && (
              <div className="ml-auto flex items-center gap-2">
                {pages && pages.length > 1 && (
                  <span className="text-xs text-slate-400">
                    p.{currentPage?.page_number}
                  </span>
                )}
                <button
                  onClick={saveEdit}
                  disabled={saveBusy}
                  className="rounded bg-emerald-600 px-4 py-1.5 text-sm font-medium text-white transition-colors hover:bg-emerald-500 disabled:opacity-50"
                >
                  {saveBusy ? '…' : t('masters.save')}
                </button>
                <button
                  onClick={() => setEditingResult(false)}
                  disabled={saveBusy}
                  className="rounded border border-slate-300 px-3 py-1.5 text-sm text-slate-600 hover:bg-slate-50"
                >
                  {t('common.cancel')}
                </button>
              </div>
            )}
          </div>
          <div className="flex-1 overflow-auto p-4">
            {resultTab === 'fields' && doc.extracted_json && (
              <FieldsPanel
                documentId={doc.id}
                filename={doc.original_filename}
                extraction={doc.extracted_json}
                fieldMatches={fieldMatches}
                onChanged={invalidateAll}
                onFieldHover={onFieldHover}
                onMatchClick={(match, anchor) => setPopup({ match, anchor })}
              />
            )}
            {resultTab === 'markdown' && editingResult && (
              <ResultEditor key={editNonce} initialValue={draft} onChange={setDraft} />
            )}
            {resultTab === 'markdown' &&
              !editingResult &&
              (markdown != null ? (
                <div ref={markdownRef} className="markdown-body text-sm">
                  <MatchableMarkdown
                    markdown={markdown}
                    matches={matches ?? []}
                    onMatchClick={(match, anchor) => setPopup({ match, anchor })}
                  />
                </div>
              ) : (
                <p className="py-12 text-center text-slate-400">
                  {processing ? t('common.loading') : '—'}
                </p>
              ))}
            {resultTab === 'lines' && (
              <RegionTextPanel
                regions={regions}
                hovered={hoveredRegion}
                onHover={setHoveredRegion}
                scrollTo={scrollToRegion}
              />
            )}
            {resultTab === 'json' &&
              (pageResult ? (
                <pre className="overflow-x-auto text-xs leading-5 text-slate-700">
                  {JSON.stringify(pageResult.layout_json, null, 2)}
                </pre>
              ) : (
                <p className="py-12 text-center text-slate-400">—</p>
              ))}
          </div>
        </section>
      </div>

      {popup && (
        <MatchPopup
          match={popup.match}
          anchor={popup.anchor}
          busy={linkBusy}
          onLink={() => actOnMatch('link')}
          onDismiss={() => actOnMatch('dismiss')}
          onClose={() => setPopup(null)}
        />
      )}
    </div>
  );
}
