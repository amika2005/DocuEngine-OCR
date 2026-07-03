import { useEffect, useMemo, useRef } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { getAccessToken } from './client';

export interface ServerEvent {
  topic: string;
  company_id: string;
  data: Record<string, unknown>;
}

/** Subscribes to the tenant-filtered SSE stream and invokes onEvent for every
 *  topic matching one of the given prefixes ('' matches everything). */
export function useEvents(
  topicPrefix: string | string[],
  onEvent: (event: ServerEvent) => void,
) {
  const prefixes = useMemo(
    () => (Array.isArray(topicPrefix) ? topicPrefix : [topicPrefix]),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [Array.isArray(topicPrefix) ? topicPrefix.join('|') : topicPrefix],
  );

  useEffect(() => {
    const token = getAccessToken();
    if (!token) return;
    const source = new EventSource(`/api/v1/events?token=${encodeURIComponent(token)}`);
    source.onmessage = (message) => {
      try {
        const event = JSON.parse(message.data) as ServerEvent;
        if (event.topic && prefixes.some((prefix) => event.topic.startsWith(prefix))) {
          onEvent(event);
        }
      } catch {
        /* ignore malformed events */
      }
    };
    return () => source.close();
  }, [prefixes, onEvent]);
}

/** Live-refresh helper: invalidates the given query keys when any matching
 *  event arrives, debounced so a 100-page batch doesn't refetch per page. */
export function useLiveInvalidate(
  topicPrefixes: string | string[],
  queryKeys: string[][],
  debounceMs = 800,
) {
  const queryClient = useQueryClient();
  const timer = useRef<ReturnType<typeof setTimeout>>();
  const keysRef = useRef(queryKeys);
  keysRef.current = queryKeys;

  const onEvent = useMemo(
    () => () => {
      clearTimeout(timer.current);
      timer.current = setTimeout(() => {
        for (const key of keysRef.current) {
          queryClient.invalidateQueries({ queryKey: key });
        }
      }, debounceMs);
    },
    [queryClient, debounceMs],
  );

  useEvents(topicPrefixes, onEvent);

  useEffect(() => () => clearTimeout(timer.current), []);
}
