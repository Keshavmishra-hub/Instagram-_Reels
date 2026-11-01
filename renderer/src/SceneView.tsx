import React from 'react';
import {AbsoluteFill, Easing, interpolate, useCurrentFrame} from 'remotion';
import type {Brand, SceneT, Transition, WordT} from './types';
import {MediaLayer} from './components/MediaLayer';
import {Backdrop} from './components/Backdrop';
import {InfoStack, StatCallouts} from './components/Overlays';
import {ChartScene, ComparisonScene, IconScene, KineticScene, QuoteScene, StatScene, TimelineScene} from './scenes/Graphics';
import {MapScene} from './scenes/MapScene';

const entrance = (transition: Transition, frame: number, overlap: number): React.CSSProperties => {
  if (overlap <= 0 || transition === 'cut') return {};
  const e = interpolate(frame, [0, overlap], [0, 1], {extrapolateLeft: 'clamp', extrapolateRight: 'clamp', easing: Easing.out(Easing.cubic)});
  switch (transition) {
    case 'slide_up':
      return {transform: `translateY(${(1 - e) * 100}%)`};
    case 'slide_left':
      return {transform: `translateX(${(1 - e) * 100}%)`};
    case 'zoom':
      return {transform: `scale(${1.28 - 0.28 * e})`, opacity: e};
    case 'whip':
      return {transform: `translateX(${(1 - e) * 75}%)`, filter: `blur(${(1 - e) * 36}px)`, opacity: Math.min(1, e * 1.6)};
    case 'wipe':
      return {clipPath: `inset(0 ${(1 - e) * 100}% 0 0)`};
    default:
      return {opacity: e};
  }
};

export const SceneView: React.FC<{
  scene: SceneT;
  brand: Brand;
  words: WordT[];
  base: string;
  durationInFrames: number;
  overlapIn: number;
  index: number;
  fps: number;
  showInfo?: boolean;
}> = ({scene, brand, words, base, durationInFrames, overlapIn, index, fps, showInfo = true}) => {
  const frame = useCurrentFrame();
  const duration = scene.end - scene.start;
  const style = entrance(scene.transition, frame, overlapIn);
  const isMedia = scene.kind === 'footage' || scene.kind === 'photo';
  const sceneFrames = durationInFrames;

  let background: React.ReactNode;
  if (isMedia && scene.media) {
    background = <MediaLayer media={scene.media} base={base} brand={brand} durationInFrames={sceneFrames} seed={index} />;
  } else if (scene.background) {
    background = <MediaLayer media={scene.background} base={base} brand={brand} durationInFrames={sceneFrames} dim={0.62} blur={4} seed={index} />;
  } else if (scene.kind !== 'map') {
    background = <Backdrop brand={brand} seed={index * 1.7} />;
  }

  let main: React.ReactNode = null;
  switch (scene.kind) {
    case 'stat':
      main = <StatScene brand={brand} scene={scene} duration={duration} />;
      break;
    case 'chart':
      main = <ChartScene brand={brand} scene={scene} duration={duration} />;
      break;
    case 'timeline':
      main = <TimelineScene brand={brand} scene={scene} words={words} duration={duration} />;
      break;
    case 'comparison':
      main = <ComparisonScene brand={brand} scene={scene} timeBase={scene.start - overlapIn / fps} />;
      break;
    case 'icon':
      main = <IconScene brand={brand} scene={scene} />;
      break;
    case 'quote':
      main = <QuoteScene brand={brand} scene={scene} />;
      break;
    case 'map':
      main = <MapScene brand={brand} scene={scene} duration={duration} />;
      break;
    case 'kinetic':
    case 'title':
      main = <KineticScene brand={brand} scene={scene} />;
      break;
    default:
      main = scene.params.headline || scene.params.text ? <KineticScene brand={brand} scene={scene} top={scene.subtitle_position === 'upper' ? 980 : 360} /> : null;
  }

  // shift overlay timing so they are relative to the scene's own timeline (which starts at start - overlap)
  const overlaySceneStart = scene.start - overlapIn / fps;
  return (
    <AbsoluteFill style={{overflow: 'hidden', ...style}}>
      {background}
      {main}
      <StatCallouts brand={brand} overlays={scene.overlays} sceneStart={overlaySceneStart} />
      {showInfo ? <InfoStack brand={brand} scene={scene} /> : null}
    </AbsoluteFill>
  );
};
