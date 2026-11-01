export type Brand = {
  key: string;
  name: string;
  handle: string;
  watermark: boolean;
  progress_bar: boolean;
  colors: {
    background: string;
    surface: string;
    primary: string;
    secondary: string;
    text: string;
    muted: string;
    danger: string;
    map_ocean: string;
    map_land: string;
    map_border: string;
  };
  fonts: {display: string; body: string; subtitle: string};
  subtitles: {case: 'upper' | 'sentence'; size: number; max_words: number; max_chars: number; style: 'outline' | 'box'};
  grade: {vignette: number; grain: number; contrast: number; saturation: number};
  script: string;
};

export type WordT = {text: string; start: number; end: number; beat: string; emphasis: boolean};

export type Cue = {start: number; end: number; words: number[]};

export type Media = {
  src: string;
  type: 'video' | 'image';
  width: number;
  height: number;
  duration: number;
  credit?: string;
  playbackRate?: number;
};

export type OverlayT = {kind: 'stat' | 'label' | 'highlight'; text: string; at: number; position: 'top' | 'center' | 'bottom'};

export type SceneKind =
  | 'footage'
  | 'photo'
  | 'map'
  | 'stat'
  | 'chart'
  | 'timeline'
  | 'kinetic'
  | 'comparison'
  | 'icon'
  | 'quote'
  | 'title';

export type Transition = 'cut' | 'fade' | 'slide_up' | 'slide_left' | 'zoom' | 'whip' | 'wipe';

export type SceneT = {
  id: string;
  start: number;
  end: number;
  kind: SceneKind;
  params: Record<string, any>;
  media?: Media | null;
  background?: Media | null;
  overlays: OverlayT[];
  transition: Transition;
  subtitle_position: 'lower' | 'upper' | 'center';
  label?: string | null;
  sources: string[];
  words: number[];
  section: string;
};

export type ReelProps = {
  fps: number;
  width: number;
  height: number;
  duration: number;
  title: string;
  brand: Brand;
  scenes: SceneT[];
  words: WordT[];
  cues: Cue[];
  assetsBase: string;
  endCard: {question: string; sourcesNote: string};
  showSubtitles: boolean;
};

export type CoverProps = {
  brand: Brand;
  headline: string;
  highlight: string;
  kicker: string;
  background?: Media | null;
  scene?: SceneT | null;
  assetsBase: string;
};
