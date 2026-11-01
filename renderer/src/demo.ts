import type {ReelProps} from './types';

// Demo data used by Remotion Studio and the visual self-test (python -m reelforge selftest-render).
// Text is placeholder layout copy, not factual content.
const brand: ReelProps['brand'] = {
  key: 'default',
  name: 'Midnight Documentary',
  handle: '@massenthusiast',
  watermark: true,
  progress_bar: true,
  colors: {
    background: '#0A0F1C',
    surface: '#121A2E',
    primary: '#FFC93C',
    secondary: '#4FD1C5',
    text: '#FFFFFF',
    muted: '#A3ADC6',
    danger: '#FF6B6B',
    map_ocean: '#060A14',
    map_land: '#1B2540',
    map_border: '#2F3D63',
  },
  fonts: {display: 'Anton', body: 'Inter', subtitle: 'Montserrat'},
  subtitles: {case: 'upper', size: 64, max_words: 3, max_chars: 22, style: 'outline'},
  grade: {vignette: 0.42, grain: 0.05, contrast: 1.06, saturation: 1.04},
  script: 'latin',
};

const sc = (id: string, start: number, end: number, kind: any, params: any, extra: any = {}) => ({
  id,
  start,
  end,
  kind,
  params,
  media: null,
  background: null,
  overlays: [],
  transition: 'fade',
  subtitle_position: 'lower',
  label: null,
  sources: ['Demo source'],
  words: [],
  section: 'story',
  ...extra,
});

export const demoProps: ReelProps = {
  fps: 30,
  width: 1080,
  height: 1920,
  duration: 24,
  title: 'Layout demo',
  brand,
  assetsBase: '',
  showSubtitles: true,
  endCard: {question: 'Which scene style works best?', sourcesNote: 'Sources in caption'},
  words: [
    {text: 'Layout', start: 0.2, end: 0.6, beat: 'B1', emphasis: false},
    {text: 'demo', start: 0.65, end: 1.0, beat: 'B1', emphasis: true},
    {text: 'only.', start: 1.05, end: 1.5, beat: 'B1', emphasis: false},
  ],
  cues: [{start: 0.2, end: 1.8, words: [0, 1, 2]}],
  scenes: [
    sc('SC1', 0, 3, 'kinetic', {text: 'Placeholder headline for layout', highlight: ['layout'], kicker: 'Demo'}, {transition: 'cut', section: 'hook'}),
    sc('SC2', 3, 7, 'map', {center: [15.6, 78.2], zoom: 7, highlight: ['Norway'], marker: {lon: 15.6, lat: 78.2, label: 'Marker label', sublabel: 'Sub label'}}),
    sc('SC3', 7, 10, 'stat', {value: 1234567, decimals: 0, label: 'Demo statistic label', sublabel: 'demo only', kicker: 'Kicker'}, {transition: 'zoom', overlays: [{kind: 'label', text: 'Callout', at: 8.2, position: 'top'}]}),
    sc('SC4', 10, 14, 'chart', {type: 'bar', title: 'Demo bar chart', unit: 'units', data: [{label: 'A', value: 17}, {label: 'B', value: 55}, {label: 'C', value: 120}, {label: 'D', value: 239}]}, {transition: 'slide_up'}),
    sc('SC5', 14, 17, 'timeline', {events: [{label: '2001', text: 'Demo event one'}, {label: '2010', text: 'Demo event two'}, {label: '2020', text: 'Demo event three'}]}, {transition: 'wipe'}),
    sc('SC6', 17, 20, 'comparison', {title: 'Then vs now', left: {label: 'Then', value: '17', note: 'demo'}, right: {label: 'Now', value: '239', note: 'demo'}}, {transition: 'whip'}),
    sc('SC7', 20, 24, 'chart', {type: 'line', title: 'Demo line chart', unit: 'units', data: [{label: '1950', value: 17}, {label: '1970', value: 21}, {label: '1990', value: 54}, {label: '2010', value: 121}, {label: '2024', value: 239}]}, {transition: 'slide_left', section: 'ending'}),
  ],
};
