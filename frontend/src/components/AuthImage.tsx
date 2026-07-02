import { useEffect, useState, type ImgHTMLAttributes } from 'react';
import { fetchBlobUrl } from '../api/client';

interface Props extends Omit<ImgHTMLAttributes<HTMLImageElement>, 'src' | 'onError'> {
  path: string; // API path, e.g. /pages/<id>/image
  onLoadError?: () => void;
}

/** <img> for JWT-protected endpoints: fetches with Authorization and renders
 *  from an object URL (revoked on unmount). */
export default function AuthImage({ path, onLoadError, ...imgProps }: Props) {
  const [url, setUrl] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    let objectUrl: string | null = null;
    setUrl(null);
    fetchBlobUrl(path)
      .then((blobUrl) => {
        objectUrl = blobUrl;
        if (active) setUrl(blobUrl);
        else URL.revokeObjectURL(blobUrl);
      })
      .catch(() => {
        if (active) onLoadError?.();
      });
    return () => {
      active = false;
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [path]);

  if (!url) return <div className="h-full w-full animate-pulse bg-slate-200" />;
  return <img src={url} {...imgProps} />;
}
