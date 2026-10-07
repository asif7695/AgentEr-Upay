import { cx } from "@/components/neu";

// App mark in the upay palette (our own "U" monogram, not upay's trademark logo): white tile, upay-blue U, yellow dot.
export function Logo({ size = 36, className }: { size?: number; className?: string }) {
  return (
    <svg width={size} height={size} viewBox="0 0 40 40" role="img" aria-label="AgentEr Upay" className={cx("shrink-0", className)}>
      <rect x="1" y="1" width="38" height="38" rx="11" fill="#FFFFFF" stroke="#D5DDEE" strokeWidth="1" />
      <path d="M12.5 11.5v10a7.5 7.5 0 0 0 15 0v-10" fill="none" stroke="#1A4FD6" strokeWidth="4" strokeLinecap="round" />
      <circle cx="28.5" cy="10.5" r="3.4" fill="#FFC20E" />
    </svg>
  );
}

/** "AgentEr Upay" with "Upay" in brand yellow (on blue bands) or brand blue (`onLight`, on white surfaces). */
export function Wordmark({ className, onLight = false }: { className?: string; onLight?: boolean }) {
  return (
    <span className={cx("font-extrabold tracking-tight", onLight && "wordmark-on-light", className)}>
      AgentEr <span className="wordmark-upay">Upay</span>
    </span>
  );
}
