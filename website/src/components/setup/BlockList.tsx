import type { Platform } from '../../lib/platform';
import type { Block } from '../../setup/types';
import { BlockView } from './BlockView';

interface BlockListProps {
  blocks: readonly Block[];
  platform: Platform;
  className?: string;
}

/** A run of blocks with even spacing. The order never changes, so the position is the key. */
export function BlockList({ blocks, platform, className = '' }: BlockListProps) {
  return (
    <div className={`space-y-3 ${className}`.trim()}>
      {blocks.map((block, index) => (
        <BlockView key={index} block={block} platform={platform} />
      ))}
    </div>
  );
}
