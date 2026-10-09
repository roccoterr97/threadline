import type { Platform } from '../../lib/platform';
import { isForPlatform, type Block } from '../../setup/types';
import { Callout } from '../Callout';
import { CommandLine } from '../CommandLine';
import { InlineText } from './InlineText';
import { ItemList } from './ItemList';
import { TableView } from './TableView';
import { ValueBox } from './ValueBox';

interface BlockViewProps {
  block: Block;
  /** The reader's computer; a block meant for other ones is not shown. */
  platform: Platform;
}

/** One block of guide content, drawn as the element it is. */
export function BlockView({ block, platform }: BlockViewProps) {
  if (!isForPlatform(block, platform)) return null;
  switch (block.kind) {
    case 'paragraph':
      return (
        <p>
          <InlineText text={block.text} />
        </p>
      );
    case 'command':
      return <CommandLine command={block.command} what={block.what} />;
    case 'steps':
      return <ItemList items={block.items} ordered />;
    case 'bullets':
      return <ItemList items={block.items} ordered={false} />;
    case 'value':
      return <ValueBox value={block.value} what={block.what} />;
    case 'note':
    case 'warning':
      return (
        <Callout tone={block.kind}>
          <p>
            <InlineText text={block.text} />
          </p>
        </Callout>
      );
    case 'table':
      return <TableView rows={block.rows} />;
  }
}
