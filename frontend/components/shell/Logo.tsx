// Brand colours are ASSUMED (no logo file was supplied): brand navy #0D1C42 (user-specified) + warm yellow. See README.
export function Logo({ size = 36 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 40 40" role="img" aria-label="AgentEr Upay">
      <rect x="2" y="2" width="36" height="36" rx="11" fill="#0D1C42" stroke="#5C78C8" strokeWidth="1.6" />
      <path d="M12 12v9.5a8 8 0 0 0 16 0V12" fill="none" stroke="#fff" strokeWidth="3.6" strokeLinecap="round" />
      <circle cx="28" cy="11.5" r="3.4" fill="#F5B400" />
    </svg>
  );
}
