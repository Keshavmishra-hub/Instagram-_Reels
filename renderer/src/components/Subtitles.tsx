import React from 'react';
import {AbsoluteFill, interpolate, spring, useCurrentFrame, useVideoConfig} from 'remotion';
import type {Brand, Cue, SceneT, WordT} from '../types';
import {fontStack, hexToRgba, upper} from '../theme';

const POS: Record<string, number> = {lower: 1235, upper: 470, center: 900};

/**
 * Word-synchronised captions: the active cue pops in, the word being spoken lights up in the
 * accent colour, and numbers/key terms stay highlighted. Readable with the sound off.
 */
export const Subtitles: React.FC<{brand: Brand; words: WordT[]; cues: Cue[]; scenes: SceneT[]; hideAfter?: number}> = ({brand, words, cues, scenes, hideAfter}) => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const t = frame / fps;
  if (hideAfter != null && t >= hideAfter) return null;
  const cue = cues.find((c) => t >= c.start && t < c.end);
  if (!cue) return null;
  const scene = scenes.find((s) => t >= s.start && t < s.end);
  const position = scene?.subtitle_position || 'lower';
  const cueFrame = Math.round(cue.start * fps);
  const pop = spring({frame: frame - cueFrame, fps, config: {damping: 14, stiffness: 220, mass: 0.6}});
  const scale = interpolate(pop, [0, 1], [0.82, 1]);
  const size = brand.subtitles.size;
  const box = brand.subtitles.style === 'box';
  const c = brand.colors;
  return (
    <AbsoluteFill style={{pointerEvents: 'none'}}>
      <div
        style={{
          position: 'absolute',
          left: 90,
          right: 150,
          top: POS[position] - size,
          display: 'flex',
          justifyContent: 'center',
          transform: `scale(${scale})`,
          opacity: interpolate(pop, [0, 0.4], [0, 1], {extrapolateRight: 'clamp'}),
        }}
      >
        <div
          style={{
            display: 'flex',
            flexWrap: 'wrap',
            justifyContent: 'center',
            gap: `0 ${Math.round(size * 0.36)}px`,
            padding: box ? '14px 26px 18px' : 0,
            borderRadius: 18,
            background: box ? hexToRgba('#000000', 0.62) : 'transparent',
            maxWidth: 840,
          }}
        >
          {cue.words.map((wi) => {
            const w = words[wi];
            const active = t >= w.start - 0.03;
            const speaking = t >= w.start - 0.03 && t < w.end + 0.05;
            const color = w.emphasis ? c.primary : speaking ? c.primary : c.text;
            const wordPop = spring({frame: frame - Math.round(w.start * fps), fps, config: {damping: 12, stiffness: 260, mass: 0.5}});
            return (
              <span
                key={wi}
                style={{
                  fontFamily: fontStack(brand.fonts.subtitle, brand),
                  fontWeight: 900,
                  fontSize: size,
                  lineHeight: 1.12,
                  letterSpacing: brand.script === 'latin' ? '0.01em' : 0,
                  color,
                  opacity: active ? 1 : 0.92,
                  transform: speaking ? `scale(${interpolate(wordPop, [0, 1], [1.0, 1.05])})` : 'scale(1)',
                  display: 'inline-block',
                  WebkitTextStroke: box ? undefined : `${Math.round(size * 0.16)}px #000`,
                  paintOrder: 'stroke fill',
                  textShadow: '0 6px 22px rgba(0,0,0,0.55)',
                }}
              >
                {upper(w.text, brand)}
              </span>
            );
          })}
        </div>
      </div>
    </AbsoluteFill>
  );
};
