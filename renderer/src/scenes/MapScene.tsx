import React, {useMemo} from 'react';
import {AbsoluteFill, Easing, interpolate, spring, useCurrentFrame, useVideoConfig} from 'remotion';
import {geoGraticule10, geoInterpolate, geoOrthographic, geoPath} from 'd3-geo';
import {feature, mesh} from 'topojson-client';
// Natural Earth 1:50m via world-atlas (public domain data)
import world from 'world-atlas/countries-50m.json';
import type {Brand, SceneT} from '../types';
import {fontStack, hexToRgba} from '../theme';

const ALIASES: Record<string, string> = {
  usa: 'united states of america',
  'united states': 'united states of america',
  us: 'united states of america',
  uk: 'united kingdom',
  britain: 'united kingdom',
  'great britain': 'united kingdom',
  russia: 'russia',
  'south korea': 'south korea',
  'north korea': 'north korea',
  uae: 'united arab emirates',
  drc: 'dem. rep. congo',
  'democratic republic of the congo': 'dem. rep. congo',
  'czech republic': 'czechia',
  'ivory coast': "côte d'ivoire",
};

const W: any = world;
const COUNTRIES: any = feature(W, W.objects.countries);
const BORDERS: any = mesh(W, W.objects.countries, (a: any, b: any) => a !== b);
const LAND: any = feature(W, W.objects.land);
const GRATICULE = geoGraticule10();

const norm = (s: string) => {
  const k = s.trim().toLowerCase();
  return ALIASES[k] || k;
};

type Pt = {lon: number; lat: number; label?: string; sublabel?: string};

export const MapScene: React.FC<{brand: Brand; scene: SceneT; duration: number}> = ({brand, scene, duration}) => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const p = scene.params;
  const c = brand.colors;
  const center: [number, number] = p.center || [p.marker?.lon ?? 0, p.marker?.lat ?? 20];
  const from: [number, number] = p.from || [center[0] - 55, Math.max(-30, Math.min(30, center[1] * 0.35))];
  const zoom: number = Math.max(1, Number(p.zoom ?? 3));
  const total = Math.max(1, duration * fps);
  const rotP = interpolate(frame, [0, Math.min(total * 0.45, fps * 1.8)], [0, 1], {extrapolateRight: 'clamp', easing: Easing.inOut(Easing.cubic)});
  const zoomP = interpolate(frame, [Math.min(total * 0.2, fps * 0.6), Math.min(total * 0.8, fps * 3.2)], [0, 1], {
    extrapolateLeft: 'clamp',
    extrapolateRight: 'clamp',
    easing: Easing.inOut(Easing.cubic),
  });
  const lon = from[0] + (center[0] - from[0]) * rotP;
  const lat = from[1] + (center[1] - from[1]) * rotP;
  const base = 410;
  const scale = base * Math.pow(zoom, zoomP);
  const cy = 900;
  const projection = useMemo(() => geoOrthographic().clipAngle(90).precision(0.4), []);
  projection.rotate([-lon, -lat, 0]).scale(scale).translate([540, cy]);
  const path = geoPath(projection);
  const highlight: string[] = (p.highlight || []).map(norm);
  const hiFeatures = COUNTRIES.features.filter((f: any) => highlight.includes(String(f.properties?.name || '').toLowerCase()));
  const glow = 0.55 + 0.25 * Math.sin(frame / 7);
  const markers: Pt[] = [...(p.marker ? [p.marker] : []), ...(p.points || [])];
  const markerIn = spring({frame: frame - Math.round(Math.min(total * 0.6, fps * 2.4)), fps, config: {damping: 13, stiffness: 140}});
  const routes: [number, number][][] = p.routes || (p.route ? [p.route] : []);
  const routeP = interpolate(frame, [Math.min(total * 0.45, fps * 1.6), Math.min(total * 0.95, fps * 3.8)], [0, 1], {
    extrapolateLeft: 'clamp',
    extrapolateRight: 'clamp',
    easing: Easing.inOut(Easing.quad),
  });

  return (
    <AbsoluteFill style={{backgroundColor: c.map_ocean}}>
      <AbsoluteFill style={{background: `radial-gradient(circle at 50% ${cy / 19.2}%, ${hexToRgba(c.secondary, 0.05)} 0%, rgba(0,0,0,0) 55%)`}} />
      <svg width={1080} height={1920} style={{position: 'absolute', inset: 0}}>
        <defs>
          <radialGradient id="ocean" cx="45%" cy="40%" r="65%">
            <stop offset="0%" stopColor={c.secondary} stopOpacity={0.08} />
            <stop offset="100%" stopColor={c.map_ocean} stopOpacity={0} />
          </radialGradient>
          <filter id="glow" x="-50%" y="-50%" width="200%" height="200%">
            <feGaussianBlur stdDeviation="10" result="b" />
            <feMerge>
              <feMergeNode in="b" />
              <feMergeNode in="SourceGraphic" />
            </feMerge>
          </filter>
        </defs>
        <path d={path({type: 'Sphere'} as any) || ''} fill={c.map_ocean} />
        <path d={path({type: 'Sphere'} as any) || ''} fill="url(#ocean)" stroke={hexToRgba(c.secondary, 0.3)} strokeWidth={2} />
        <path d={path(GRATICULE) || ''} fill="none" stroke={hexToRgba(c.text, 0.07)} strokeWidth={1.2} />
        <path d={path(LAND) || ''} fill={c.map_land} />
        <path d={path(BORDERS) || ''} fill="none" stroke={c.map_border} strokeWidth={1.3} />
        {hiFeatures.map((f: any, i: number) => (
          <path key={i} d={path(f) || ''} fill={hexToRgba(c.primary, 0.85)} stroke={c.primary} strokeWidth={2.5} filter="url(#glow)" opacity={glow + 0.2} />
        ))}
        {routes.map((r, i) => {
          if (r.length < 2) return null;
          const interp = geoInterpolate(r[0], r[r.length - 1]);
          const steps = 64;
          const coords = Array.from({length: Math.max(2, Math.round(steps * routeP))}, (_, k) => interp((k / steps) * 1));
          const line = path({type: 'LineString', coordinates: coords} as any) || '';
          return <path key={i} d={line} fill="none" stroke={c.primary} strokeWidth={7} strokeDasharray="2 16" strokeLinecap="round" filter="url(#glow)" />;
        })}
        {markers.map((m, i) => {
          const xy = projection([m.lon, m.lat]);
          if (!xy) return null;
          const s = i === 0 ? markerIn : spring({frame: frame - Math.round(total * 0.6) - i * 6, fps, config: {damping: 13, stiffness: 140}});
          const pulse = (frame % 40) / 40;
          return (
            <g key={i} transform={`translate(${xy[0]},${xy[1]})`} opacity={s}>
              <circle r={22 + 60 * pulse} fill="none" stroke={c.primary} strokeWidth={4} opacity={1 - pulse} />
              <circle r={16 * s} fill={c.primary} stroke="#000" strokeWidth={3} />
            </g>
          );
        })}
      </svg>
      {markers.map((m, i) => {
        const xy = projection([m.lon, m.lat]);
        if (!xy || !m.label) return null;
        const s = i === 0 ? markerIn : spring({frame: frame - Math.round(total * 0.6) - i * 6, fps, config: {damping: 13, stiffness: 140}});
        const cardW = 400;
        const toLeft = xy[0] > 520;
        const x = toLeft ? Math.max(60, xy[0] - 70 - cardW) : Math.min(1080 - 150 - cardW, xy[0] + 70);
        const y = Math.max(330, Math.min(1040, xy[1] - 70));
        return (
          <React.Fragment key={`l${i}`}>
            <svg width={1080} height={1920} style={{position: 'absolute', inset: 0, opacity: s}}>
              <line x1={xy[0]} y1={xy[1]} x2={toLeft ? x + cardW : x} y2={y + 60} stroke={c.primary} strokeWidth={3} />
            </svg>
            <div
              style={{
                position: 'absolute',
                left: x,
                top: y,
                width: cardW,
                opacity: s,
                transform: `translateX(${(1 - s) * (toLeft ? -24 : 24)}px)`,
                background: hexToRgba('#000000', 0.7),
                border: `2px solid ${hexToRgba(c.primary, 0.85)}`,
                borderRadius: 16,
                padding: '14px 22px',
                boxSizing: 'border-box',
              }}
            >
              <div style={{fontFamily: fontStack(brand.fonts.display, brand), fontSize: 50, color: c.text, lineHeight: 1, textTransform: brand.script === 'latin' ? 'uppercase' : 'none'}}>{m.label}</div>
              {m.sublabel ? <div style={{fontFamily: fontStack(brand.fonts.body, brand), fontSize: 28, fontWeight: 700, color: c.primary, marginTop: 6}}>{m.sublabel}</div> : null}
            </div>
          </React.Fragment>
        );
      })}
      {p.title ? (
        <div style={{position: 'absolute', top: 300, left: 80, right: 150, textAlign: 'center', fontFamily: fontStack(brand.fonts.display, brand), fontSize: 70, color: c.text, textTransform: brand.script === 'latin' ? 'uppercase' : 'none', textShadow: '0 8px 30px rgba(0,0,0,0.7)'}}>
          {p.title}
        </div>
      ) : null}
    </AbsoluteFill>
  );
};
