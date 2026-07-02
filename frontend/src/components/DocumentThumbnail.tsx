import { useState } from 'react';
import type { Document } from '../api/types';
import AuthImage from './AuthImage';

/** First-page preview for the grid view. Falls back to a file icon while the
 *  document is still queued (thumbnail 404s until rasterization ran). */
export default function DocumentThumbnail({ document }: { document: Document }) {
  const [failed, setFailed] = useState(false);
  const hasPages = document.page_count > 0 && !failed;

  return (
    <div className="flex aspect-[3/4] items-center justify-center overflow-hidden bg-slate-100">
      {hasPages ? (
        <AuthImage
          path={`/documents/${document.id}/thumbnail`}
          onLoadError={() => setFailed(true)}
          className="h-full w-full object-cover object-top"
          alt=""
        />
      ) : (
        <span className="text-5xl opacity-40" aria-hidden>
          {document.original_filename.toLowerCase().endsWith('.pdf') ? '📄' : '🖼️'}
        </span>
      )}
    </div>
  );
}
