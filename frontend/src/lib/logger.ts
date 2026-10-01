/**
 * The only place in the dashboard allowed to write to the browser console.
 *
 * Output is structured (one object, never a bare string) so it can be read in
 * the browser's developer tools. Never pass message text, email addresses or
 * anything from `body` fields — identifiers and codes only.
 */

type LogFields = Record<string, string | number | boolean | null>;

interface LogRecord extends LogFields {
  event: string;
  level: 'warn' | 'error';
}

function emit(record: LogRecord): void {
  /* eslint-disable-next-line no-console --
     Structured logging sink. The browser console is the only transport a static
     site has; every other module logs through this function. */
  console[record.level](record);
}

export function logWarning(event: string, fields: LogFields = {}): void {
  emit({ ...fields, event, level: 'warn' });
}

export function logError(event: string, fields: LogFields = {}): void {
  emit({ ...fields, event, level: 'error' });
}
