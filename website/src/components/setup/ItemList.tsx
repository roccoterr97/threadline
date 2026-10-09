import { InlineText } from './InlineText';

interface ItemListProps {
  items: readonly string[];
  /** Numbered when the order matters. */
  ordered: boolean;
}

/** A numbered or bulleted list of guide text. */
export function ItemList({ items, ordered }: ItemListProps) {
  const Tag = ordered ? 'ol' : 'ul';
  return (
    <Tag className={`space-y-1 pl-6 ${ordered ? 'list-decimal' : 'list-disc'}`}>
      {items.map((item) => (
        <li key={item}>
          <InlineText text={item} />
        </li>
      ))}
    </Tag>
  );
}
