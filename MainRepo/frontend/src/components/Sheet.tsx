import { useEffect, useRef, type ReactNode } from "react";

export function Sheet({ title, onClose, children, chip, full }: {
  title: string; onClose: () => void; children: ReactNode; chip?: ReactNode; full?: boolean;
}) {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    ref.current?.focus();
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);
  return (
    <div className="sheet-layer" role="presentation">
      <div className="sheet-backdrop" onClick={onClose} />
      <div className={`sheet${full ? " sheet-full" : ""}`} role="dialog" aria-modal="true" aria-label={title} tabIndex={-1} ref={ref}>
        <div className="sheet-grabber" aria-hidden />
        <div className="sheet-head">
          <h2>{title}</h2>
          {chip}
          <button className="icon-btn" onClick={onClose} aria-label="Close">
            <svg width="14" height="14" viewBox="0 0 14 14" aria-hidden><path d="M2 2l10 10M12 2L2 12" stroke="currentColor" strokeWidth="2" strokeLinecap="round" /></svg>
          </button>
        </div>
        <div className="sheet-body">{children}</div>
      </div>
    </div>
  );
}
