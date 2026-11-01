import React from 'react';
import {AbsoluteFill, Easing, interpolate, spring, useCurrentFrame, useVideoConfig} from 'remotion';
import type {Brand, SceneT, WordT} from '../types';
import {fontStack, formatNumber, hexToRgba} from '../theme';
import {Icon} from '../components/Overlays';

const fit = (text: string, maxWidth: number, maxSize: number, minSize: number, factor = 0.5) => {
  const longest = Math.max(...text.split('\n').map((l) => l.length), 1);
  return Math.max(minSize, Math.min(maxSize, Math.floor(maxWidth / (longest * factor))));
};

const useSceneTime = () => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  return {frame, fps, t: frame / fps};
};

/* ------------------------------------------------------------------------------------------ */
/* Big number                                                                                  */
/* ------------------------------------------------------------------------------------------ */
export const StatScene: React.FC<{brand: Brand; scene: SceneT; duration: number}> = ({brand, scene}) => {
  const {frame, fps} = useSceneTime();
  const p = scene.params;
  const value = Number(p.value ?? 0);
  const from = Number(p.from ?? 0);
  const decimals = Number(p.decimals ?? (Number.isInteger(value) ? 0 : 1));
  const locale = p.locale || 'en-US';
  const prog = interpolate(frame, [8, 8 + fps * 1.1], [0, 1], {extrapolateLeft: 'clamp', extrapolateRight: 'clamp', easing: Easing.out(Easing.cubic)});
  const shown = p.count === false ? value : from + (value - from) * prog;
  const numText = `${p.prefix ?? ''}${formatNumber(shown, decimals, locale)}${p.suffix ?? ''}`;
  const unit = p.unit ? String(p.unit) : '';
  const size = fit(numText, 900, 270, 120, 0.46);
  const enter = spring({frame: frame - 4, fps, config: {damping: 15, stiffness: 140}});
  const labelIn = spring({frame: frame - 18, fps, config: {damping: 18, stiffness: 120}});
  const c = brand.colors;
  const breathe = interpolate(frame, [0, fps * 8], [1, 1.06], {extrapolateRight: 'clamp'});
  return (
    <AbsoluteFill style={{justifyContent: 'center', alignItems: 'center', transform: `scale(${breathe})`}}>
      <div style={{position: 'absolute', top: 410, left: 80, right: 150, textAlign: 'center'}}>
        {p.kicker ? (
          <div style={{fontFamily: fontStack(brand.fonts.body, brand), fontWeight: 800, fontSize: 34, letterSpacing: '0.18em', color: c.secondary, textTransform: 'uppercase', marginBottom: 18, opacity: enter}}>
            {p.kicker}
          </div>
        ) : null}
        <div
          style={{
            fontFamily: fontStack(brand.fonts.display, brand),
            fontSize: size,
            lineHeight: 0.95,
            color: c.primary,
            transform: `scale(${interpolate(enter, [0, 1], [0.6, 1])})`,
            opacity: enter,
            textShadow: `0 0 60px ${hexToRgba(c.primary, 0.35)}, 0 12px 40px rgba(0,0,0,0.6)`,
            fontVariantNumeric: 'tabular-nums',
          }}
        >
          {numText}
        </div>
        {unit ? (
          <div style={{fontFamily: fontStack(brand.fonts.display, brand), fontSize: Math.round(size * 0.36), color: c.text, marginTop: 6, opacity: enter, textTransform: 'uppercase'}}>
            {unit}
          </div>
        ) : null}
        <div style={{height: 8, width: `${interpolate(labelIn, [0, 1], [0, 46])}%`, background: c.primary, margin: '30px auto 26px', borderRadius: 4}} />
        <div
          style={{
            fontFamily: fontStack(brand.fonts.body, brand),
            fontWeight: 800,
            fontSize: fit(String(p.label || ''), 860, 56, 36, 0.52),
            lineHeight: 1.18,
            color: c.text,
            opacity: labelIn,
            transform: `translateY(${(1 - labelIn) * 30}px)`,
          }}
        >
          {p.label}
        </div>
        {p.sublabel ? (
          <div style={{fontFamily: fontStack(brand.fonts.body, brand), fontWeight: 500, fontSize: 32, color: c.muted, marginTop: 14, opacity: labelIn}}>{p.sublabel}</div>
        ) : null}
      </div>
    </AbsoluteFill>
  );
};

/* ------------------------------------------------------------------------------------------ */
/* Kinetic typography                                                                          */
/* ------------------------------------------------------------------------------------------ */
export const KineticScene: React.FC<{brand: Brand; scene: SceneT; top?: number}> = ({brand, scene, top}) => {
  const {frame, fps} = useSceneTime();
  const p = scene.params;
  const text: string = String(p.text || p.headline || '').trim();
  const highlight: string[] = (p.highlight || []).map((h: string) => h.toLowerCase());
  const words = text.split(/\s+/).filter(Boolean);
  const latin = brand.script === 'latin';
  // Anton (Latin) and Teko (Devanagari) are condensed display faces; other scripts use wider Noto Sans
  const factor = latin ? 0.3 : brand.script === 'deva' ? 0.36 : 0.55;
  const size = fit(text, 880, 168, 84, factor) * (words.length > 6 ? 0.82 : 1);
  const c = brand.colors;
  const isHi = (w: string) => highlight.some((h) => h.split(/\s+/).includes(w.toLowerCase().replace(/[^\p{L}\p{M}\p{N}%°.\-]/gu, '')));
  return (
    <AbsoluteFill>
      <div style={{position: 'absolute', top: top ?? 560, left: 80, right: 150, textAlign: 'center'}}>
        {p.kicker ? (
          <div
            style={{
              display: 'inline-block',
              fontFamily: fontStack(brand.fonts.body, brand),
              fontWeight: 800,
              fontSize: 32,
              letterSpacing: '0.2em',
              color: '#0b0b0b',
              background: c.secondary,
              padding: '8px 18px',
              borderRadius: 8,
              marginBottom: 28,
              opacity: interpolate(frame, [0, 8], [0, 1], {extrapolateRight: 'clamp'}),
              textTransform: 'uppercase',
            }}
          >
            {p.kicker}
          </div>
        ) : null}
        <div style={{display: 'flex', flexWrap: 'wrap', justifyContent: 'center', gap: `0 ${Math.round(size * 0.3)}px`}}>
          {words.map((w, i) => {
            const s = spring({frame: frame - 3 - i * 3, fps, config: {damping: 14, stiffness: 170}});
            const hi = isHi(w);
            const mark = interpolate(frame, [10 + i * 3, 22 + i * 3], [0, 1], {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'});
            return (
              <span key={i} style={{position: 'relative', display: 'inline-block', margin: '4px 0'}}>
                {hi ? (
                  <span
                    style={{
                      position: 'absolute',
                      left: -10,
                      right: -10,
                      top: '12%',
                      bottom: '6%',
                      background: c.primary,
                      transform: `scaleX(${mark}) skewX(-6deg)`,
                      transformOrigin: 'left center',
                      borderRadius: 6,
                    }}
                  />
                ) : null}
                <span
                  style={{
                    position: 'relative',
                    fontFamily: fontStack(brand.fonts.display, brand),
                    fontSize: size,
                    lineHeight: 1.04,
                    color: hi ? '#0b0b0b' : c.text,
                    textTransform: latin ? 'uppercase' : 'none',
                    display: 'inline-block',
                    transform: `translateY(${(1 - s) * 60}px) rotate(${(1 - s) * 4}deg)`,
                    opacity: s,
                    textShadow: hi ? 'none' : '0 10px 34px rgba(0,0,0,0.55)',
                  }}
                >
                  {w}
                </span>
              </span>
            );
          })}
        </div>
        {p.subtext ? (
          <div style={{marginTop: 30, fontFamily: fontStack(brand.fonts.body, brand), fontWeight: 600, fontSize: 40, color: c.muted, opacity: interpolate(frame, [18, 30], [0, 1], {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'})}}>
            {p.subtext}
          </div>
        ) : null}
      </div>
    </AbsoluteFill>
  );
};

/* ------------------------------------------------------------------------------------------ */
/* Charts                                                                                      */
/* ------------------------------------------------------------------------------------------ */
type Datum = {label: string; value: number; display?: string};

export const ChartScene: React.FC<{brand: Brand; scene: SceneT; duration: number}> = ({brand, scene, duration}) => {
  const {frame, fps} = useSceneTime();
  const p = scene.params;
  const data: Datum[] = (p.data || []).map((d: any) => ({label: String(d.label), value: Number(d.value), display: d.display}));
  const type: string = p.type || (data.length > 7 ? 'line' : 'bar');
  const c = brand.colors;
  const decimals = Number(p.decimals ?? 0);
  const max = Math.max(...data.map((d) => d.value), 1) * 1.08;
  const hiIdx = p.highlight ?? data.length - 1;
  // lines draw across most of the scene (continuous motion); bars grow quickly then hold
  const growFrames = type === 'line' ? Math.max(fps * 1.2, duration * fps * 0.78) : Math.min(fps * 1.6, Math.max(fps * 0.8, duration * fps * 0.45));
  const push = interpolate(frame, [0, Math.max(1, duration * fps)], [1, 1.05]);
  const titleIn = spring({frame, fps, config: {damping: 18, stiffness: 120}});
  const W = 860;
  const H = 600;
  const left = 110;
  const top = 470;
  return (
    <AbsoluteFill>
      <div style={{position: 'absolute', top: 300, left: 80, right: 150, textAlign: 'left', opacity: titleIn, transform: `translateY(${(1 - titleIn) * 24}px)`}}>
        <div style={{fontFamily: fontStack(brand.fonts.display, brand), fontSize: fit(String(p.title || ''), 840, 78, 50, 0.42), color: c.text, textTransform: brand.script === 'latin' ? 'uppercase' : 'none', lineHeight: 1.02}}>
          {p.title}
        </div>
        {p.unit ? <div style={{fontFamily: fontStack(brand.fonts.body, brand), fontSize: 32, fontWeight: 600, color: c.muted, marginTop: 8}}>{p.unit}</div> : null}
      </div>
      <svg width={1080} height={1920} style={{position: 'absolute', inset: 0, transform: `scale(${push})`, transformOrigin: '50% 45%'}}>
        <defs>
          <linearGradient id="barGrad" x1="0" x2="0" y1="0" y2="1">
            <stop offset="0%" stopColor={c.primary} />
            <stop offset="100%" stopColor={c.primary} stopOpacity={0.55} />
          </linearGradient>
          <linearGradient id="barGradMuted" x1="0" x2="0" y1="0" y2="1">
            <stop offset="0%" stopColor={c.text} stopOpacity={0.55} />
            <stop offset="100%" stopColor={c.text} stopOpacity={0.22} />
          </linearGradient>
        </defs>
        <line x1={left - 20} x2={left + W} y1={top + H} y2={top + H} stroke={hexToRgba(c.text, 0.35)} strokeWidth={3} />
        {type === 'line'
          ? (() => {
              const n = data.length;
              const pts = data.map((d, i) => [left + (n === 1 ? W / 2 : (i / (n - 1)) * (W - 40)), top + H - (d.value / max) * H] as const);
              const prog = interpolate(frame, [6, 6 + growFrames], [0, 1], {extrapolateLeft: 'clamp', extrapolateRight: 'clamp', easing: Easing.inOut(Easing.cubic)});
              const path = pts.map((pt, i) => `${i ? 'L' : 'M'}${pt[0]},${pt[1]}`).join(' ');
              let length = 0;
              for (let i = 1; i < pts.length; i++) length += Math.hypot(pts[i][0] - pts[i - 1][0], pts[i][1] - pts[i - 1][1]);
              const area = `${path} L${pts[pts.length - 1][0]},${top + H} L${pts[0][0]},${top + H} Z`;
              return (
                <g>
                  <clipPath id="reveal">
                    <rect x={0} y={0} width={left + (W + 40) * prog} height={1920} />
                  </clipPath>
                  <path d={area} fill={hexToRgba(c.primary, 0.16)} clipPath="url(#reveal)" />
                  <path d={path} fill="none" stroke={c.primary} strokeWidth={9} strokeLinejoin="round" strokeLinecap="round" strokeDasharray={length} strokeDashoffset={length * (1 - prog)} />
                  {pts.map((pt, i) => {
                    const shown = prog >= (n === 1 ? 0 : i / (n - 1)) - 0.001;
                    const isHi = i === hiIdx;
                    const showLabel = isHi || i === 0 || n <= 6;
                    return shown ? (
                      <g key={i}>
                        <circle cx={pt[0]} cy={pt[1]} r={isHi ? 16 : 9} fill={isHi ? c.primary : c.text} stroke={c.background} strokeWidth={4} />
                        {showLabel ? (
                          <text x={pt[0]} y={pt[1] - 30} fill={isHi ? c.primary : c.text} fontSize={isHi ? 52 : 34} fontFamily={fontStack(brand.fonts.display, brand)} textAnchor="middle">
                            {data[i].display ?? formatNumber(data[i].value, decimals)}
                          </text>
                        ) : null}
                        {showLabel ? (
                          <text x={pt[0]} y={top + H + 52} fill={c.muted} fontSize={30} fontWeight={700} fontFamily={fontStack(brand.fonts.body, brand)} textAnchor="middle">
                            {data[i].label}
                          </text>
                        ) : null}
                      </g>
                    ) : null;
                  })}
                </g>
              );
            })()
          : data.map((d, i) => {
              const n = data.length;
              const gap = 26;
              const bw = Math.min(170, (W - gap * (n - 1)) / n);
              const x = left + i * (bw + gap) + (W - (n * bw + (n - 1) * gap)) / 2;
              const s = interpolate(frame, [6 + i * 5, 6 + i * 5 + growFrames * 0.7], [0, 1], {extrapolateLeft: 'clamp', extrapolateRight: 'clamp', easing: Easing.out(Easing.cubic)});
              const h = (d.value / max) * H * s;
              const isHi = i === hiIdx;
              return (
                <g key={i}>
                  <rect x={x} y={top + H - h} width={bw} height={h} rx={14} fill={isHi ? 'url(#barGrad)' : 'url(#barGradMuted)'} />
                  <text x={x + bw / 2} y={top + H - h - 22} fill={isHi ? c.primary : c.text} fontSize={isHi ? 54 : 40} fontFamily={fontStack(brand.fonts.display, brand)} textAnchor="middle" opacity={s}>
                    {d.display ?? formatNumber(d.value * s, decimals)}
                  </text>
                  <text x={x + bw / 2} y={top + H + 52} fill={c.muted} fontSize={n > 5 ? 26 : 32} fontWeight={700} fontFamily={fontStack(brand.fonts.body, brand)} textAnchor="middle">
                    {d.label}
                  </text>
                </g>
              );
            })}
      </svg>
    </AbsoluteFill>
  );
};

/* ------------------------------------------------------------------------------------------ */
/* Timeline                                                                                    */
/* ------------------------------------------------------------------------------------------ */
export const TimelineScene: React.FC<{brand: Brand; scene: SceneT; words: WordT[]; duration: number}> = ({brand, scene, words, duration}) => {
  const {frame, fps} = useSceneTime();
  const events: {label: string; text: string}[] = scene.params.events || [];
  const c = brand.colors;
  // reveal each event when its label (e.g. a year) is spoken; otherwise spread evenly
  const sceneWords = scene.words.map((i) => words[i]).filter(Boolean);
  const times = events.map((e, i) => {
    const key = e.label.toLowerCase().replace(/[^\p{L}\p{M}\p{N}]/gu, '');
    const w = sceneWords.find((x) => x.text.toLowerCase().replace(/[^\p{L}\p{M}\p{N}]/gu, '').includes(key));
    return w ? Math.max(0, w.start - scene.start - 0.15) : 0.25 + (i * Math.max(0.6, duration - 1)) / Math.max(1, events.length);
  });
  const top = 420;
  const rowH = Math.min(210, 640 / Math.max(1, events.length));
  const lineProg = interpolate(frame, [0, fps * Math.max(0.8, duration * 0.8)], [0, 1], {extrapolateRight: 'clamp'});
  const active = times.reduce((acc, t, i) => (frame / fps >= t ? i : acc), -1);
  return (
    <AbsoluteFill>
      <div style={{position: 'absolute', left: 170, top, width: 6, height: rowH * events.length * lineProg, background: `linear-gradient(${c.primary}, ${hexToRgba(c.primary, 0.2)})`, borderRadius: 3}} />
      {events.map((e, i) => {
        const s = spring({frame: frame - Math.round(times[i] * fps), fps, config: {damping: 14, stiffness: 150}});
        const isActive = i === active;
        return (
          <div key={i} style={{position: 'absolute', left: 120, top: top + i * rowH - 10, right: 150, display: 'flex', alignItems: 'flex-start', gap: 34, opacity: s, transform: `translateX(${(1 - s) * 60}px)`}}>
            <div style={{width: 106, height: 106, flex: '0 0 auto', display: 'flex', alignItems: 'center', justifyContent: 'center'}}>
              <div style={{width: isActive ? 44 : 30, height: isActive ? 44 : 30, borderRadius: 999, background: isActive ? c.primary : c.surface, border: `5px solid ${c.primary}`, boxShadow: isActive ? `0 0 34px ${c.primary}` : 'none'}} />
            </div>
            <div style={{marginTop: 6}}>
              <div style={{fontFamily: fontStack(brand.fonts.display, brand), fontSize: isActive ? 84 : 66, color: isActive ? c.primary : c.text, lineHeight: 1}}>{e.label}</div>
              <div style={{fontFamily: fontStack(brand.fonts.body, brand), fontWeight: 700, fontSize: 38, color: isActive ? c.text : c.muted, marginTop: 8, lineHeight: 1.2, maxWidth: 620}}>{e.text}</div>
            </div>
          </div>
        );
      })}
    </AbsoluteFill>
  );
};

/* ------------------------------------------------------------------------------------------ */
/* Comparison                                                                                  */
/* ------------------------------------------------------------------------------------------ */
export const ComparisonScene: React.FC<{brand: Brand; scene: SceneT; timeBase?: number}> = ({brand, scene, timeBase}) => {
  const {frame, fps} = useSceneTime();
  const p = scene.params;
  const c = brand.colors;
  const sides = [p.left || {}, p.right || {}];
  // cards can appear exactly when they are mentioned in the narration (params.left.at / right.at, seconds)
  const appearAt = (sd: any, i: number) => (sd.at != null && timeBase != null ? Math.max(0, Math.round((sd.at - timeBase) * fps)) : 6 + i * 10);
  return (
    <AbsoluteFill>
      {p.title ? (
        <div style={{position: 'absolute', top: 330, left: 80, right: 150, textAlign: 'center', fontFamily: fontStack(brand.fonts.display, brand), fontSize: 74, color: c.text, textTransform: brand.script === 'latin' ? 'uppercase' : 'none'}}>
          {p.title}
        </div>
      ) : null}
      {sides.map((sd: any, i: number) => {
        const s = spring({frame: frame - appearAt(sd, i), fps, config: {damping: 15, stiffness: 140}});
        const accent = i === 1 ? c.primary : c.secondary;
        return (
          <div
            key={i}
            style={{
              position: 'absolute',
              left: 90,
              right: 160,
              top: 470 + i * 350,
              height: 300,
              borderRadius: 28,
              background: hexToRgba(c.surface, 0.88),
              border: `3px solid ${hexToRgba(accent, 0.7)}`,
              boxShadow: '0 24px 60px rgba(0,0,0,0.45)',
              padding: '34px 40px',
              opacity: s,
              transform: `translateX(${(1 - s) * (i ? 120 : -120)}px)`,
            }}
          >
            <div style={{fontFamily: fontStack(brand.fonts.body, brand), fontWeight: 800, fontSize: 36, color: accent, letterSpacing: '0.08em', textTransform: 'uppercase'}}>{sd.label}</div>
            <div style={{fontFamily: fontStack(brand.fonts.display, brand), fontSize: fit(String(sd.value ?? ''), 760, 150, 70, 0.45), color: c.text, lineHeight: 1.05, marginTop: 10}}>{sd.value}</div>
            {sd.note ? <div style={{fontFamily: fontStack(brand.fonts.body, brand), fontWeight: 600, fontSize: 32, color: c.muted, marginTop: 6}}>{sd.note}</div> : null}
          </div>
        );
      })}
      <div
        style={{
          position: 'absolute',
          right: 120,
          top: 735,
          display: 'flex',
          justifyContent: 'flex-end',
          opacity: interpolate(frame, [appearAt(sides[1], 1), appearAt(sides[1], 1) + 8], [0, 1], {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'}),
        }}
      >
        <div style={{width: 120, height: 120, borderRadius: 999, background: c.primary, color: '#0b0b0b', display: 'flex', alignItems: 'center', justifyContent: 'center', fontFamily: fontStack(brand.fonts.display, brand), fontSize: 54, boxShadow: '0 10px 40px rgba(0,0,0,0.5)'}}>
          {p.divider || 'VS'}
        </div>
      </div>
    </AbsoluteFill>
  );
};

/* ------------------------------------------------------------------------------------------ */
/* Icon / illustration                                                                         */
/* ------------------------------------------------------------------------------------------ */
export const IconScene: React.FC<{brand: Brand; scene: SceneT}> = ({brand, scene}) => {
  const {frame, fps} = useSceneTime();
  const p = scene.params;
  const c = brand.colors;
  const s = spring({frame: frame - 2, fps, config: {damping: 12, stiffness: 120}});
  const ring = (frame % 45) / 45;
  const icons: string[] = p.icons_svg || (p.icon_svg ? [p.icon_svg] : []);
  return (
    <AbsoluteFill>
      <div style={{position: 'absolute', top: 440, left: 0, right: 70, display: 'flex', justifyContent: 'center'}}>
        <div style={{position: 'relative', width: 420, height: 420, transform: `scale(${s})`}}>
          <div style={{position: 'absolute', inset: -40 * ring, borderRadius: 999, border: `4px solid ${hexToRgba(c.primary, 0.5 * (1 - ring))}`}} />
          <div
            style={{
              position: 'absolute',
              inset: 0,
              borderRadius: 999,
              background: `radial-gradient(circle at 50% 40%, ${hexToRgba(c.primary, 0.28)}, ${hexToRgba(c.surface, 0.9)} 70%)`,
              border: `4px solid ${hexToRgba(c.primary, 0.85)}`,
              boxShadow: `0 0 80px ${hexToRgba(c.primary, 0.35)}`,
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              gap: 20,
            }}
          >
            {icons.slice(0, 2).map((svg, i) => (
              <Icon key={i} svg={svg} size={icons.length > 1 ? 150 : 230} color={c.text} strokeWidth={1.5} />
            ))}
          </div>
        </div>
      </div>
      <div style={{position: 'absolute', top: 925, left: 80, right: 150, textAlign: 'center', opacity: interpolate(frame, [10, 20], [0, 1], {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'})}}>
        <div style={{fontFamily: fontStack(brand.fonts.display, brand), fontSize: fit(String(p.label || ''), 860, 104, 58, 0.42), color: c.text, textTransform: brand.script === 'latin' ? 'uppercase' : 'none', lineHeight: 1.02}}>
          {p.label}
        </div>
        {p.caption ? <div style={{fontFamily: fontStack(brand.fonts.body, brand), fontWeight: 600, fontSize: 38, color: c.muted, marginTop: 16}}>{p.caption}</div> : null}
      </div>
    </AbsoluteFill>
  );
};

/* ------------------------------------------------------------------------------------------ */
/* Verified quote                                                                              */
/* ------------------------------------------------------------------------------------------ */
export const QuoteScene: React.FC<{brand: Brand; scene: SceneT}> = ({brand, scene}) => {
  const {frame, fps} = useSceneTime();
  const p = scene.params;
  const c = brand.colors;
  const s = spring({frame, fps, config: {damping: 18, stiffness: 110}});
  return (
    <AbsoluteFill>
      <div style={{position: 'absolute', top: 400, left: 100, right: 160, opacity: s, transform: `translateY(${(1 - s) * 30}px)`}}>
        <div style={{fontFamily: 'Georgia, serif', fontSize: 240, color: c.primary, lineHeight: 0.6, height: 120}}>“</div>
        <div style={{fontFamily: fontStack(brand.fonts.body, brand), fontWeight: 700, fontSize: fit(String(p.quote || ''), 2600, 64, 42, 0.5), lineHeight: 1.28, color: c.text}}>{p.quote}</div>
        <div style={{marginTop: 36, fontFamily: fontStack(brand.fonts.body, brand), fontWeight: 800, fontSize: 38, color: c.primary}}>— {p.author}</div>
        {p.role ? <div style={{fontFamily: fontStack(brand.fonts.body, brand), fontWeight: 500, fontSize: 30, color: c.muted, marginTop: 6}}>{p.role}</div> : null}
      </div>
    </AbsoluteFill>
  );
};
