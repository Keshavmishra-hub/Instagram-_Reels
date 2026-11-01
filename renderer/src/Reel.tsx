import React from 'react';
import {AbsoluteFill, Sequence, useVideoConfig} from 'remotion';
import type {ReelProps} from './types';
import {ensureFonts} from './theme';
import {SceneView} from './SceneView';
import {EndCard, Grain, Handle, ProgressBar, Vignette} from './components/Overlays';
import {Subtitles} from './components/Subtitles';

const OVERLAP = 9; // frames of overlap used by non-cut transitions

export const Reel: React.FC<ReelProps> = (props) => {
  ensureFonts();
  const {fps} = useVideoConfig();
  const {brand, scenes, words, cues} = props;
  return (
    <AbsoluteFill style={{backgroundColor: brand.colors.background}}>
      {scenes.map((s, i) => {
        const startF = Math.round(s.start * fps);
        const endF = Math.max(startF + 1, Math.round(s.end * fps));
        const overlapIn = i === 0 || s.transition === 'cut' ? 0 : Math.min(OVERLAP, Math.round((scenes[i - 1].end - scenes[i - 1].start) * fps / 2));
        const next = scenes[i + 1];
        const overlapOut = next && next.transition !== 'cut' ? OVERLAP : 0;
        const from = startF - overlapIn;
        const dur = endF - startF + overlapIn + overlapOut;
        return (
          <Sequence key={s.id} from={from} durationInFrames={dur} name={`${s.id} ${s.kind}`}>
            <SceneView scene={s} brand={brand} words={words} base={props.assetsBase} durationInFrames={dur} overlapIn={overlapIn} index={i} fps={fps} />
          </Sequence>
        );
      })}
      <Vignette brand={brand} />
      <Grain brand={brand} />
      {props.showSubtitles ? <Subtitles brand={brand} words={words} cues={cues} scenes={scenes} hideAfter={Math.max(0, props.duration - 1.45)} /> : null}
      <EndCard brand={brand} question={props.endCard.question} sourcesNote={props.endCard.sourcesNote} from={Math.max(0, props.duration - 1.45)} />
      <ProgressBar brand={brand} total={props.duration} />
      <Handle brand={brand} />
    </AbsoluteFill>
  );
};
