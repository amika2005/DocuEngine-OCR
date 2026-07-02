import { useEffect, useRef, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { useQuery } from '@tanstack/react-query';
import CodeMirror from '@uiw/react-codemirror';
import { markdown as markdownLang } from '@codemirror/lang-markdown';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { api } from '../../api/client';
import type { Correction, OcrResult } from '../../api/types';
import PageViewer from '../../components/PageViewer';

export default function CorrectionEditorPage() {
  const { pageId } = useParams<{ pageId: string }>();
  const { t } = useTranslation();
  const navigate = useNavigate();
  const [text, setText] = useState('');
  const [correctionId, setCorrectionId] = useState<string | null>(null);
  const [showPreview, setShowPreview] = useState(false);
  const [notice, setNotice] = useState('');
  const saveTimer = useRef<ReturnType<typeof setTimeout>>();

  const { data: result } = useQuery({
    queryKey: ['page-result', pageId],
    queryFn: () => api<OcrResult>(`/pages/${pageId}/result`),
  });

  useEffect(() => {
    if (result) setText(result.markdown);
  }, [result]);

  async function ensureCorrection(markdown: string): Promise<string> {
    if (correctionId) return correctionId;
    const created = await api<Correction>(`/pages/${pageId}/corrections`, {
      method: 'POST',
      body: JSON.stringify({ corrected_markdown: markdown }),
    });
    setCorrectionId(created.id);
    return created.id;
  }

  function onChange(value: string) {
    setText(value);
    clearTimeout(saveTimer.current);
    saveTimer.current = setTimeout(async () => {
      const id = await ensureCorrection(value);
      await api(`/corrections/${id}`, {
        method: 'PUT',
        body: JSON.stringify({ corrected_markdown: value }),
      });
      setNotice(t('editor.saved'));
      setTimeout(() => setNotice(''), 1500);
    }, 800);
  }

  async function onSubmit() {
    clearTimeout(saveTimer.current);
    const id = await ensureCorrection(text);
    await api(`/corrections/${id}`, {
      method: 'PUT',
      body: JSON.stringify({ corrected_markdown: text }),
    });
    await api(`/corrections/${id}/submit`, { method: 'POST' });
    alert(t('editor.submitted'));
    navigate(-1);
  }

  return (
    <div>
      <div className="mb-4 flex items-center gap-3">
        <h1 className="text-xl font-bold">{t('editor.title')}</h1>
        {result?.avg_confidence != null && (
          <span className="text-sm text-slate-500">
            {t('detail.confidence')}: {(result.avg_confidence * 100).toFixed(1)}%
          </span>
        )}
        <span className="text-sm text-green-600">{notice}</span>
        <div className="ml-auto flex gap-2">
          <button
            onClick={() => setShowPreview((value) => !value)}
            className="rounded border border-slate-300 bg-white px-3 py-1.5 text-sm hover:bg-slate-50"
          >
            {t('editor.preview')}
          </button>
          <button
            onClick={onSubmit}
            className="rounded bg-slate-900 px-4 py-1.5 text-sm text-white hover:bg-slate-700"
          >
            {t('editor.submit')}
          </button>
        </div>
      </div>

      <div className="grid grid-cols-2 gap-4">
        <section className="rounded-lg border border-slate-200 bg-white p-3">
          <PageViewer path={`/pages/${pageId}/image`} />
        </section>
        <section className="rounded-lg border border-slate-200 bg-white p-3">
          {showPreview ? (
            <div className="markdown-body max-h-[70vh] overflow-auto text-sm">
              <ReactMarkdown remarkPlugins={[remarkGfm]}>{text}</ReactMarkdown>
            </div>
          ) : (
            <CodeMirror
              value={text}
              height="70vh"
              extensions={[markdownLang()]}
              onChange={onChange}
            />
          )}
        </section>
      </div>
    </div>
  );
}
