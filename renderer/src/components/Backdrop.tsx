import React from 'react';
import {AbsoluteFill, interpolate, useCurrentFrame} from 'remotion';
import type {Brand} from '../types';
import {hexToRgba} from '../theme';

/** Moving, textured gradient used behind graphic scenes (stats, charts, maps, kinetic type). */
export const Backdrop: React.FC<{brand: Brand; seed?: number; accent?: string; grid?: boolean}> = ({brand, seed = 0, accent, grid = true}) => {
  const frame = useCurrentFrame();
  const c = brand.colors;
  const a = accent || c.primary;
  const t = frame / 30;
  const x1 = 30 + 18 * Math.sin(t * 0.35 + seed);
  const y1 = 22 + 10 * Math.cos(t * 0.27 + seed * 2);
  const x2 = 72 + 14 * Math.cos(t * 0.31 + seed);
  const y2 = 78 + 8 * Math.sin(t * 0.22 + seed);
  const drift = interpolate(frame % 600, [0, 600], [0, 120]);
  return (
    <AbsoluteFill style={{backgroundColor: c.background}}>
      <AbsoluteFill
        style={{
          background: `radial-gradient(circle at ${x1}% ${y1}%, ${hexToRgba(a, 0.22)} 0%, rgba(0,0,0,0) 42%),
                       radial-gradient(circle at ${x2}% ${y2}%, ${hexToRgba(c.secondary, 0.16)} 0%, rgba(0,0,0,0) 45%),
                       linear-gradient(180deg, ${c.surface} 0%, ${c.background} 70%)`,
        }}
      />
      {grid ? (
        <AbsoluteFill
          style={{
            opacity: 0.11,
            backgroundImage: `linear-gradient(${hexToRgba(c.text, 0.5)} 1px, transparent 1px), linear-gradient(90deg, ${hexToRgba(c.text, 0.5)} 1px, transparent 1px)`,
            backgroundSize: '90px 90px',
            backgroundPosition: `0px ${drift}px`,
            maskImage: 'radial-gradient(circle at 50% 45%, black 0%, transparent 75%)',
            WebkitMaskImage: 'radial-gradient(circle at 50% 45%, black 0%, transparent 75%)',
          }}
        />
      ) : null}
    </AbsoluteFill>
  );
};
