import { CopyButton } from './CopyButton';

interface CommandLineProps {
  command: string;
  /** What the line is, for the copy button's name: "the install line". */
  what: string;
}

/** One line to paste into a terminal, with a button that copies it. */
export function CommandLine({ command, what }: CommandLineProps) {
  return (
    <div className="flex items-center gap-3 rounded-token-md border border-line bg-surface px-3 py-2">
      <code className="min-w-0 flex-1 overflow-x-auto whitespace-pre font-mono text-sm text-ink">
        {command}
      </code>
      <CopyButton text={command} what={what} />
    </div>
  );
}
