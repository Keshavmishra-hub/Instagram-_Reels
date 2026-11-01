import React from 'react';
import {AbsoluteFill} from 'remotion';
import type {CoverProps} from './types';
import {ensureFonts, fontStack, hexToRgba} from './theme';
import {SceneView} from './SceneView';
import {MediaLayer} from './components/MediaLayer';
import {Backdrop} from './components/Backdrop';
import {Grain, Vignette} from './components/Overlays';

/**
 * Reel cover: a strong frame from the reel + a short headline. The headline sits inside the
 * centre 3:4 area so it survives Instagram's profile-grid crop.
 */
export const Cover: React.FC<CoverProps> = ({brand, headline, highlight, kicker, background, scene, assetsBase}) => {
  ensureFonts();
  const c = brand.colors;
  const latin = brand.script === 'latin';
  const words = headline.split(/\s+/).filter(Boolean);
  const hi = highlight.toLowerCase().split(/\s+/).filter(Boolean);
  const longest = Math.max(...words.map((w) => w.length), 4);
  const size = Math.min(190, Math.floor(880 / (longest * (latin ? 0.52 : 0.6))), words.length > 5 ? 150 : 190);
  return (
    <AbsoluteFill style={{backgroundColor: c.background}}>
      {background ? (
        <MediaLayer media={background} base={assetsBase} brand={brand} durationInFrames={1} dim={0.35} />
      ) : scene ? (
        // rendered as a still at ~85% of the scene (see render_cover), when its animation has completed
        <SceneView scene={{...scene, overlays: [], sources: [], label: null}} brand={brand} words={[]} base={assetsBase} durationInFrames={Math.round((scene.end - scene.start) * 30)} overlapIn={0} index={0} fps={30} showInfo={false} />
      ) : (
        <Backdrop brand={brand} />
      )}
      <AbsoluteFill style={{background: 'linear-gradient(180deg, rgba(0,0,0,0.25) 0%, rgba(0,0,0,0.55) 45%, rgba(0,0,0,0.85) 100%)'}} />
      <div style={{position: 'absolute', left: 70, right: 70, top: 980, transform: 'translateY(-50%)', textAlign: 'center'}}>
        {kicker ? (
          <div style={{display: 'inline-block', fontFamily: fontStack(brand.fonts.body, brand), fontWeight: 800, fontSize: 40, letterSpacing: '0.16em', color: '#0b0b0b', background: c.secondary, padding: '10px 22px', borderRadius: 10, marginBottom: 30, textTransform: 'uppercase'}}>
            {kicker}
          </div>
        ) : null}
        <div style={{display: 'flex', flexWrap: 'wrap', justifyContent: 'center', gap: `0 ${Math.round(size * 0.2)}px`}}>
          {words.map((w, i) => {
            const isHi = hi.includes(w.toLowerCase().replace(/[^\p{L}\p{M}\p{N}%°.\-]/gu, ''));
            return (
              <span
                key={i}
                style={{
                  fontFamily: fontStack(brand.fonts.display, brand),
                  fontSize: size,
                  lineHeight: 1.02,
                  color: isHi ? '#0b0b0b' : c.text,
                  background: isHi ? c.primary : 'transparent',
                  padding: isHi ? '0 14px' : 0,
                  borderRadius: 10,
                  textTransform: latin ? 'uppercase' : 'none',
                  textShadow: isHi ? 'none' : '0 10px 40px rgba(0,0,0,0.6)',
                  margin: '6px 0',
                }}
              >
                {w}
              </span>
            );
          })}
        </div>
        {brand.handle ? (
          <div style={{marginTop: 40, fontFamily: fontStack(brand.fonts.body, brand), fontWeight: 700, fontSize: 36, color: hexToRgba(c.text, 0.85)}}>{brand.handle}</div>
        ) : null}
      </div>
      <Vignette brand={brand} />
      <Grain brand={brand} />
    </AbsoluteFill>
  );
};
