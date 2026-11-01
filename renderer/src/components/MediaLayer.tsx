import React from 'react';
import {AbsoluteFill, Img, Loop, OffthreadVideo, interpolate, useCurrentFrame, useVideoConfig} from 'remotion';
import type {Brand, Media} from '../types';
import {mediaUrl} from '../theme';

type Props = {
  media: Media;
  base: string;
  brand: Brand;
  durationInFrames: number;
  dim?: number; // 0..1 darkening for graphic overlays
  blur?: number;
  seed?: number;
};

/**
 * Photo or footage with slow camera motion ("Ken Burns"), a consistent colour grade and
 * legibility gradients. Landscape photos are shown whole on a blurred fill instead of being
 * cropped, so documentary evidence is never cut off.
 */
export const MediaLayer: React.FC<Props> = ({media, base, brand, durationInFrames, dim = 0, blur = 0, seed = 0}) => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const src = mediaUrl(media, base);
  const p = interpolate(frame, [0, Math.max(1, durationInFrames)], [0, 1], {extrapolateRight: 'clamp'});
  const dir = seed % 4;
  const zoomFrom = media.type === 'video' ? 1.02 : 1.06;
  const zoomTo = media.type === 'video' ? 1.09 : 1.17;
  const scale = interpolate(p, [0, 1], [zoomFrom, zoomTo]);
  const dx = [-1, 1, 0, 0][dir] * interpolate(p, [0, 1], [0, 26]);
  const dy = [0, 0, -1, 1][dir] * interpolate(p, [0, 1], [0, 30]);
  const grade = `contrast(${brand.grade.contrast}) saturate(${brand.grade.saturation}) brightness(${1 - dim * 0.55})${blur ? ` blur(${blur}px)` : ''}`;
  const aspect = media.width && media.height ? media.width / media.height : 0.5625;
  const landscapePhoto = media.type === 'image' && aspect > 0.8;

  const visual = (style: React.CSSProperties) => {
    if (media.type === 'video') {
      const clipFrames = Math.max(1, Math.floor((media.duration || 0) * fps / (media.playbackRate || 1)));
      const video = (
        <OffthreadVideo src={src} muted playbackRate={media.playbackRate || 1} style={{...style, objectFit: 'cover'}} />
      );
      return media.duration && clipFrames < durationInFrames ? <Loop durationInFrames={clipFrames}>{video}</Loop> : video;
    }
    return <Img src={src} style={{...style, objectFit: landscapePhoto ? 'contain' : 'cover'}} />;
  };

  return (
    <AbsoluteFill style={{backgroundColor: brand.colors.background, overflow: 'hidden'}}>
      {landscapePhoto ? (
        <>
          <AbsoluteFill style={{transform: 'scale(1.25)', filter: `blur(38px) brightness(0.45) saturate(1.1)`}}>
            <Img src={src} style={{width: '100%', height: '100%', objectFit: 'cover'}} />
          </AbsoluteFill>
          <AbsoluteFill style={{justifyContent: 'center', alignItems: 'center', transform: `translate(${dx}px, ${dy}px) scale(${scale})`, filter: grade}}>
            <div style={{width: 1000, height: 1000 / aspect, maxHeight: 1250, boxShadow: '0 30px 80px rgba(0,0,0,0.6)', borderRadius: 18, overflow: 'hidden'}}>
              {visual({width: '100%', height: '100%'})}
            </div>
          </AbsoluteFill>
        </>
      ) : (
        <AbsoluteFill style={{transform: `translate(${dx}px, ${dy}px) scale(${scale})`, filter: grade}}>
          {visual({width: '100%', height: '100%'})}
        </AbsoluteFill>
      )}
      <AbsoluteFill
        style={{
          background:
            'linear-gradient(180deg, rgba(0,0,0,0.55) 0%, rgba(0,0,0,0) 22%, rgba(0,0,0,0) 48%, rgba(0,0,0,0.62) 78%, rgba(0,0,0,0.78) 100%)',
        }}
      />
    </AbsoluteFill>
  );
};
