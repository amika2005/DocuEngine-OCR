import { useEffect } from 'react';
import { getAccessToken } from './client';

export interface ServerEvent {
  topic: string;
  company_id: string;
  data: Record<string, unknown>;
}

/** Subscribes to the tenant-filtered SSE stream and invokes onEvent for
 *  every topic matching the given prefix (e.g. `document.<id>.`). */
export function useEvents(topicPrefix: string, onEvent: (event: ServerEvent) => void) {
  useEffect(() => {
    const token = getAccessToken();
    if (!token) return;
    const source = new EventSource(`/api/v1/events?token=${encodeURIComponent(token)}`);
    source.onmessage = (message) => {
      try {
        const event = JSON.parse(message.data) as ServerEvent;
        if (event.topic?.startsWith(topicPrefix)) onEvent(event);
      } catch {
        /* ignore malformed events */
      }
    };
    return () => source.close();
  }, [topicPrefix, onEvent]);
}
