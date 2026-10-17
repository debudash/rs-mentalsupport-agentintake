// The app header: the design system's cover as a responsive banner, in the same column as the
// page (the form width for Clients, wide for staff). Name left, blocks right, and the 988 crisis
// line right under the blocks. Full size on the sign-in screen; a short band once signed in.

// Pills drifting right like a current, cut from the cover (x, y, width; 12px tall).
const PILLS: Record<'river' | 'tint' | 'deep', [number, number, number][]> = {
  river: [
    [32, 40, 56],
    [48, 64, 80],
    [40, 88, 64],
    [64, 112, 72],
    [56, 136, 48],
    [80, 160, 56],
    [72, 184, 40],
    [96, 208, 40],
  ],
  tint: [
    [184, 112, 64],
    [200, 136, 88],
    [192, 160, 56],
    [216, 184, 72],
    [232, 208, 48],
  ],
  deep: [
    [344, 184, 64],
    [368, 208, 88],
  ],
};

function Art() {
  return (
    <svg
      className="banner-art"
      viewBox="0 0 480 248"
      preserveAspectRatio="xMaxYMax slice"
      aria-hidden="true"
      focusable="false"
    >
      <rect className="banner-river" x="16" y="-24" width="136" height="264" rx="12" />
      <rect className="banner-tint" x="168" y="88" width="136" height="152" rx="12" />
      <rect className="banner-deep" x="320" y="40" width="160" height="200" rx="12" />
      <rect className="banner-ok" x="168" y="60" width="48" height="12" rx="6" />
      {Object.entries(PILLS).map(([on, pills]) =>
        pills.map(([x, y, w]) => (
          <rect
            key={`${on}-${x}-${y}`}
            className={`banner-pill on-${on}`}
            x={x}
            y={y}
            width={w}
            height="12"
            rx="6"
          />
        )),
      )}
    </svg>
  );
}

export function Banner({
  compact = false,
  wide = false,
  onSignOut,
}: {
  compact?: boolean;
  wide?: boolean;
  onSignOut?: () => void;
}) {
  const classes = ['banner', compact && 'compact', wide && 'wide'].filter(Boolean).join(' ');
  return (
    <header className={classes}>
      <div className="banner-inner">
        <div className="banner-words">
          <p className="banner-name">
            <span>Riverside</span> <span>Counseling</span>
          </p>
          {!compact && (
            <p className="banner-tag">Calm, plain and safe. Help is always one tap away.</p>
          )}
        </div>
        {onSignOut && (
          <button type="button" className="secondary banner-signout" onClick={onSignOut}>
            Sign out
          </button>
        )}
        <Art />
        <a className="crisis-link banner-crisis" href="tel:988">
          In crisis? Call or text 988
        </a>
      </div>
    </header>
  );
}
