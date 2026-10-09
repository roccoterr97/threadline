import type { ReactNode } from 'react';
import { Link } from 'react-router-dom';

/**
 * The little inline markup the guide's text may carry, drawn as real
 * elements: `**bold**`, `` `code` `` and `[label](address)`. Everything
 * else is plain text, so nothing an author writes can become HTML.
 */

type Piece =
  | { kind: 'text'; text: string }
  | { kind: 'bold'; text: string }
  | { kind: 'code'; text: string }
  | { kind: 'link'; label: string; href: string };

// One pass, left to right: bold, code, or a link whose address is a web
// address or a page of this website. Anything else is text.
const MARKUP = /\*\*(.+?)\*\*|`([^`]+)`|\[([^\]]+)\]\(((?:https?:\/\/|\/)[^\s)]+)\)/g;

function parseInline(text: string): Piece[] {
  const pieces: Piece[] = [];
  let last = 0;
  for (const match of text.matchAll(MARKUP)) {
    const [whole, bold, code, label, href] = match;
    if (match.index > last) pieces.push({ kind: 'text', text: text.slice(last, match.index) });
    if (bold !== undefined) pieces.push({ kind: 'bold', text: bold });
    else if (code !== undefined) pieces.push({ kind: 'code', text: code });
    else if (label !== undefined && href !== undefined) pieces.push({ kind: 'link', label, href });
    last = match.index + whole.length;
  }
  if (last < text.length) pieces.push({ kind: 'text', text: text.slice(last) });
  return pieces;
}

const LINK_CLASSES = 'link';

function renderLink(piece: { label: string; href: string }, key: number): ReactNode {
  if (piece.href.startsWith('/')) {
    return (
      <Link key={key} to={piece.href} className={LINK_CLASSES}>
        {piece.label}
      </Link>
    );
  }
  return (
    <a key={key} href={piece.href} className={LINK_CLASSES} target="_blank" rel="noreferrer">
      {piece.label}
    </a>
  );
}

function renderPiece(piece: Piece, key: number): ReactNode {
  switch (piece.kind) {
    case 'bold':
      return <strong key={key}>{piece.text}</strong>;
    case 'code':
      return (
        <code key={key} className="rounded-token-sm bg-neutral-soft px-1 py-0.5 font-mono text-[0.9em]">
          {piece.text}
        </code>
      );
    case 'link':
      return renderLink(piece, key);
    case 'text':
      return piece.text;
  }
}

/** One run of guide text with its inline markup drawn. */
export function InlineText({ text }: { text: string }) {
  return <>{parseInline(text).map(renderPiece)}</>;
}
