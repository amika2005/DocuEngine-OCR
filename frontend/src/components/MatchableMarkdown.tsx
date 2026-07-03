import { Children, isValidElement, type ReactNode } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import type { MasterMatch } from '../api/types';

/** Markdown renderer that wraps master-match text in clickable <mark> spans:
 *  green = exact/linked (✓), amber = fuzzy (~). Matches are injected by
 *  walking rendered string children — no raw-HTML plugins, so OCR content
 *  stays safely escaped. */
export default function MatchableMarkdown({
  markdown,
  matches,
  onMatchClick,
}: {
  markdown: string;
  matches: MasterMatch[];
  onMatchClick: (match: MasterMatch, anchor: HTMLElement) => void;
}) {
  // Longest first so overlapping candidates prefer the fuller match.
  const active = [...matches]
    .filter((match) => match.status !== 'dismissed' && match.matched_text.trim())
    .sort((a, b) => b.matched_text.length - a.matched_text.length);

  function highlightString(text: string, keyPrefix: string): ReactNode[] {
    for (const match of active) {
      const index = text.indexOf(match.matched_text);
      if (index === -1) continue;
      const before = text.slice(0, index);
      const after = text.slice(index + match.matched_text.length);
      const linked = match.status === 'linked';
      const exact = match.kind === 'exact' || linked;
      return [
        ...(before ? highlightString(before, `${keyPrefix}b`) : []),
        <mark
          key={`${keyPrefix}m${match.id}`}
          onClick={(event) => onMatchClick(match, event.currentTarget)}
          className={`cursor-pointer rounded px-0.5 transition-colors ${
            exact
              ? 'bg-green-100 text-green-900 hover:bg-green-200'
              : 'bg-amber-100 text-amber-900 hover:bg-amber-200'
          } ${linked ? 'ring-1 ring-green-500' : ''}`}
          title={`${match.master_type_name} / ${match.field_label}`}
        >
          {match.matched_text}
          <span className="ml-0.5 select-none text-[10px] align-super">
            {linked ? '✓✓' : exact ? '✓' : '~'}
          </span>
        </mark>,
        ...(after ? highlightString(after, `${keyPrefix}a`) : [after]),
      ].filter((node) => node !== '');
    }
    return [text];
  }

  function walk(children: ReactNode, keyPrefix: string): ReactNode {
    return Children.map(children, (child, index) => {
      if (typeof child === 'string') {
        return highlightString(child, `${keyPrefix}-${index}-`);
      }
      if (isValidElement<{ children?: ReactNode }>(child) && child.props.children) {
        return {
          ...child,
          props: { ...child.props, children: walk(child.props.children, `${keyPrefix}-${index}`) },
        };
      }
      return child;
    });
  }

  const withHighlights =
    (Tag: keyof JSX.IntrinsicElements) =>
    ({ children, ...props }: { children?: ReactNode }) => {
      const Element = Tag as 'p';
      return <Element {...props}>{walk(children, Tag)}</Element>;
    };

  return (
    <ReactMarkdown
      remarkPlugins={[remarkGfm]}
      components={{
        p: withHighlights('p'),
        li: withHighlights('li'),
        td: withHighlights('td'),
        th: withHighlights('th'),
        h1: withHighlights('h1'),
        h2: withHighlights('h2'),
        h3: withHighlights('h3'),
      }}
    >
      {markdown}
    </ReactMarkdown>
  );
}
