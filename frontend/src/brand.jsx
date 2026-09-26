// Brand identity: real logo assets (user-supplied lockups processed to
// transparent PNGs; see scripts/process_logos.py). Light theme → metallic
// lockup; dark theme → glowing white lockup. Swap happens through theme CSS
// ([data-theme]), so "system" mode adapts automatically.
// surface="dark" forces the white variant — for surfaces that stay dark in
// BOTH themes (the floating nav's glass chip); using the theme swap there
// made the metallic mark vanish on dark glass in light mode.
import React from 'react';
import lockupLight from './assets/autostack-lockup-light.png';
import lockupDark from './assets/autostack-lockup-dark.png';
import markLight from './assets/autostack-mark-light.png';
import markDark from './assets/autostack-mark-dark.png';

export function ThemeLogo({ lockup = true, h = 26, glow = false, title = 'AutoStack', surface = 'theme' }) {
  const light = lockup ? lockupLight : markLight;
  const dark = lockup ? lockupDark : markDark;
  const forced = surface === 'dark' ? ' logo-forced-dark' : '';
  return (
    <span className={`theme-logo${glow ? ' logo-glow' : ''}${forced}`} style={{ height: h }} title={title}>
      <img className="logo-light" src={light} alt={title} />
      <img className="logo-dark" src={dark} alt="" aria-hidden="true" />
    </span>
  );
}

export function BrandMark({ size = 30, withGlow = false }) {
  return (
    <span className={`brand-tile${withGlow ? ' brand-glow' : ''}`} style={{ width: size, height: size }} aria-hidden="true">
      <svg width={size * 0.62} height={size * 0.62} viewBox="0 0 24 24" fill="none"
        stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <path d="M12 3l8 4.5-8 4.5-8-4.5L12 3z" />
        <path d="M4 12.5l8 4.5 8-4.5" opacity="0.72" />
        <path d="M4 17l8 4.5L20 17" opacity="0.4" />
      </svg>
    </span>
  );
}
