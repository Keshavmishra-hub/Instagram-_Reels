import React from 'react';
import {AbsoluteFill, Img, interpolate, spring, staticFile, useCurrentFrame, useVideoConfig} from 'remotion';
import type {Brand, OverlayT, SceneT} from '../types';
import {fontStack, hexToRgba, SAFE} from '../theme';

/** Pill that pops in exactly when the narrator says the key number/term. */
export const StatCallouts: React.FC<{brand: Brand; overlays: OverlayT[]; sceneStart: number}> = ({brand, overlays, sceneStart}) => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const tops: Record<string, number> = {top: 360, center: 820, bottom: 1040};
  return (
    <AbsoluteFill style={{pointerEvents: 'none'}}>
      {overlays.map((o, i) => {
        const at = Math.round((o.at - sceneStart) * fps);
        const s = spring({frame: frame - at, fps, config: {damping: 12, stiffness: 180}});
        if (frame < at) return null;
        const big = o.kind === 'stat';
        return (
          <div
            key={i}
            style={{
              position: 'absolute',
              top: tops[o.position] ?? 360,
              left: 0,
              right: 0,
              display: 'flex',
              justifyContent: 'center',
              transform: `translateY(${interpolate(s, [0, 1], [40, 0])}px) scale(${interpolate(s, [0, 1], [0.7, 1])})`,
              opacity: s,
            }}
          >
            <div
              style={{
                fontFamily: fontStack(big ? brand.fonts.display : brand.fonts.body, brand),
                fontSize: big ? 118 : 46,
                fontWeight: big ? 400 : 800,
                color: big ? brand.colors.primary : '#0b0b0b',
                background: big ? hexToRgba('#000000', 0.55) : brand.colors.primary,
                padding: big ? '6px 34px 14px' : '12px 28px',
                borderRadius: big ? 22 : 999,
                letterSpacing: big ? '0.01em' : '0.02em',
                textTransform: 'uppercase',
                boxShadow: '0 18px 50px rgba(0,0,0,0.45)',
                border: big ? `3px solid ${hexToRgba(brand.colors.primary, 0.75)}` : 'none',
              }}
            >
              {o.text}
            </div>
          </div>
        );
      })}
    </AbsoluteFill>
  );
};

/** Top-left stack: source tag(s) and authenticity/credit label. Top-right: handle. */
export const InfoStack: React.FC<{brand: Brand; scene: SceneT}> = ({brand, scene}) => {
  const frame = useCurrentFrame();
  const appear = interpolate(frame, [6, 16], [0, 1], {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'});
  const c = brand.colors;
  const sources = scene.sources.slice(0, 2);
  return (
    <AbsoluteFill style={{pointerEvents: 'none'}}>
      <div style={{position: 'absolute', top: SAFE.top, left: SAFE.left, display: 'flex', flexDirection: 'column', gap: 10, opacity: appear, maxWidth: 640}}>
        {sources.length ? (
          <div
            style={{
              alignSelf: 'flex-start',
              fontFamily: fontStack(brand.fonts.body, brand),
              fontSize: 25,
              fontWeight: 600,
              color: c.text,
              background: hexToRgba('#000000', 0.5),
              border: `1.5px solid ${hexToRgba(c.text, 0.18)}`,
              padding: '7px 16px',
              borderRadius: 10,
              letterSpacing: '0.02em',
            }}
          >
            <span style={{color: c.primary, fontWeight: 800}}>SOURCE</span>
            {'  '}
            {sources.join(' · ')}
          </div>
        ) : null}
        {scene.label ? (
          <div
            style={{
              alignSelf: 'flex-start',
              fontFamily: fontStack(brand.fonts.body, brand),
              fontSize: 22,
              fontStyle: 'italic',
              color: hexToRgba(c.text, 0.85),
              background: hexToRgba('#000000', 0.38),
              padding: '5px 12px',
              borderRadius: 8,
            }}
          >
            {scene.label}
          </div>
        ) : null}
      </div>
    </AbsoluteFill>
  );
};

export const Handle: React.FC<{brand: Brand}> = ({brand}) => {
  if (!brand.watermark || !brand.handle) return null;
  return (
    <div
      style={{
        position: 'absolute',
        top: SAFE.top + 4,
        right: 60,
        fontFamily: fontStack(brand.fonts.body, brand),
        fontWeight: 700,
        fontSize: 26,
        color: hexToRgba(brand.colors.text, 0.78),
        textShadow: '0 2px 10px rgba(0,0,0,0.6)',
        letterSpacing: '0.02em',
      }}
    >
      {brand.handle}
    </div>
  );
};

export const ProgressBar: React.FC<{brand: Brand; total: number}> = ({brand, total}) => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  if (!brand.progress_bar) return null;
  const p = Math.min(1, frame / Math.max(1, total * fps));
  return (
    <div style={{position: 'absolute', top: 0, left: 0, right: 0, height: 9, background: 'rgba(255,255,255,0.14)'}}>
      <div style={{width: `${p * 100}%`, height: '100%', background: brand.colors.primary, boxShadow: `0 0 14px ${brand.colors.primary}`}} />
    </div>
  );
};

export const Grain: React.FC<{brand: Brand}> = ({brand}) => {
  const frame = useCurrentFrame();
  if (!brand.grade.grain) return null;
  const tile = Math.floor(frame / 2) % 4;
  const ox = (frame * 37) % 512;
  const oy = (frame * 91) % 512;
  return (
    <AbsoluteFill
      style={{
        backgroundImage: `url(${staticFile(`textures/grain${tile}.png`)})`,
        backgroundRepeat: 'repeat',
        backgroundPosition: `${ox}px ${oy}px`,
        mixBlendMode: 'overlay',
        opacity: brand.grade.grain * 2.2,
        pointerEvents: 'none',
      }}
    />
  );
};

export const Vignette: React.FC<{brand: Brand}> = ({brand}) => (
  <AbsoluteFill
    style={{
      background: `radial-gradient(ellipse at 50% 45%, rgba(0,0,0,0) 45%, rgba(0,0,0,${brand.grade.vignette}) 100%)`,
      pointerEvents: 'none',
    }}
  />
);

/** Final seconds: question + "sources in caption" so the viewer knows where to verify. */
export const EndCard: React.FC<{brand: Brand; question: string; sourcesNote: string; from: number}> = ({brand, question, sourcesNote, from}) => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const f = frame - Math.round(from * fps);
  if (f < 0) return null;
  const s = spring({frame: f, fps, config: {damping: 16, stiffness: 120}});
  return (
    <AbsoluteFill style={{pointerEvents: 'none'}}>
      <AbsoluteFill style={{background: `rgba(0,0,0,${0.88 * s})`, backdropFilter: `blur(${18 * s}px)`}} />
      <div
        style={{
          position: 'absolute',
          top: 700,
          left: 90,
          right: 150,
          textAlign: 'center',
          transform: `translateY(${(1 - s) * 50}px)`,
          opacity: s,
        }}
      >
        {question ? (
          <div style={{fontFamily: fontStack(brand.fonts.display, brand), fontSize: 84, lineHeight: 1.05, color: brand.colors.text, textTransform: brand.script === 'latin' ? 'uppercase' : 'none'}}>
            {question}
          </div>
        ) : null}
        <div
          style={{
            marginTop: 36,
            display: 'inline-block',
            fontFamily: fontStack(brand.fonts.body, brand),
            fontSize: 34,
            fontWeight: 800,
            color: '#0b0b0b',
            background: brand.colors.primary,
            padding: '12px 28px',
            borderRadius: 999,
          }}
        >
          {sourcesNote}
        </div>
        {brand.handle ? (
          <div style={{marginTop: 26, fontFamily: fontStack(brand.fonts.body, brand), fontSize: 32, fontWeight: 700, color: hexToRgba(brand.colors.text, 0.85)}}>
            {brand.handle}
          </div>
        ) : null}
      </div>
    </AbsoluteFill>
  );
};

export const Icon: React.FC<{svg: string; size: number; color: string; strokeWidth?: number}> = ({svg, size, color, strokeWidth = 1.6}) => {
  const markup = svg
    .replace(/<!--.*?-->/gs, '')
    .replace(/width="24"/, `width="${size}"`)
    .replace(/height="24"/, `height="${size}"`)
    .replace(/stroke-width="2"/, `stroke-width="${strokeWidth}"`);
  return <div style={{width: size, height: size, color, lineHeight: 0}} dangerouslySetInnerHTML={{__html: markup}} />;
};

export const Logo: React.FC<{src?: string}> = ({src}) => (src ? <Img src={src} style={{width: 120}} /> : null);
