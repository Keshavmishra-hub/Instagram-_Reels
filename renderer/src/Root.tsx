import React from 'react';
import {Composition} from 'remotion';
import {Reel} from './Reel';
import {Cover} from './Cover';
import type {CoverProps, ReelProps} from './types';
import {demoProps} from './demo';

export const RemotionRoot: React.FC = () => (
  <>
    <Composition
      id="Reel"
      component={Reel as any}
      fps={30}
      width={1080}
      height={1920}
      durationInFrames={300}
      defaultProps={demoProps as any}
      calculateMetadata={({props}) => {
        const p = props as unknown as ReelProps;
        return {durationInFrames: Math.max(1, Math.round(p.duration * (p.fps || 30))), fps: p.fps || 30};
      }}
    />
    {/* A normal composition (not <Still>) so the cover can show any frame of the chosen scene. */}
    <Composition
      id="Cover"
      component={Cover as any}
      fps={30}
      durationInFrames={900}
      width={1080}
      height={1920}
      defaultProps={{brand: demoProps.brand, headline: 'A vault for the world’s seeds', highlight: 'seeds', kicker: 'Svalbard', assetsBase: '', background: null, scene: demoProps.scenes[1]} as CoverProps as any}
    />
  </>
);
