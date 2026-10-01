import { Button } from './Button';

interface ConfirmPanelProps {
  title: string;
  body: string;
  confirmLabel: string;
  cancelLabel: string;
  onConfirm: () => void;
  onCancel: () => void;
  isBusy: boolean;
  /** Set when the last attempt failed. */
  errorText: string | null;
}

/**
 * An "are you sure?" step shown in the page itself rather than in a pop-up, so
 * it stays keyboard-friendly and readable at phone width.
 */
export function ConfirmPanel({
  title,
  body,
  confirmLabel,
  cancelLabel,
  onConfirm,
  onCancel,
  isBusy,
  errorText,
}: ConfirmPanelProps) {
  return (
    <div className="rounded-token-lg border border-danger bg-danger-soft p-4">
      <h3 className="text-base font-semibold text-danger">{title}</h3>
      <p className="mt-1 text-ink">{body}</p>
      {errorText !== null && (
        <p role="alert" className="mt-2 text-danger">
          {errorText}
        </p>
      )}
      <div className="mt-4 flex flex-wrap gap-3">
        <Button variant="danger" onClick={onConfirm} disabled={isBusy}>
          {confirmLabel}
        </Button>
        <Button variant="secondary" onClick={onCancel} disabled={isBusy}>
          {cancelLabel}
        </Button>
      </div>
    </div>
  );
}
