import * as copy from '../copy/en';
import { PLATFORM_LABELS, PLATFORMS, type Platform } from '../lib/platform';

interface PlatformSwitcherProps {
  value: Platform;
  onChange: (platform: Platform) => void;
}

/** Three radio-like buttons: Mac, Windows, Linux. */
export function PlatformSwitcher({ value, onChange }: PlatformSwitcherProps) {
  return (
    <div role="radiogroup" aria-label={copy.platform.label} className="inline-flex gap-1 rounded-token-sm border border-line bg-surface p-1">
      {PLATFORMS.map((platform) => {
        const selected = platform === value;
        return (
          <button
            key={platform}
            type="button"
            role="radio"
            aria-checked={selected}
            onClick={() => onChange(platform)}
            className={`rounded-[0.25rem] px-3 py-1.5 text-sm font-medium transition-colors ${
              selected ? 'bg-accent text-accent-fg' : 'text-ink hover:bg-neutral-soft'
            }`}
          >
            {PLATFORM_LABELS[platform]}
          </button>
        );
      })}
    </div>
  );
}
