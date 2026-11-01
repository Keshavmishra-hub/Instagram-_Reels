import {continueRender, delayRender, staticFile} from 'remotion';
import {loadFont} from '@remotion/fonts';
import type {Brand, Media} from './types';

// Instagram UI covers the top (~220px), the bottom (~380px: caption, audio, buttons)
// and the right edge (~140px: like/comment/share). Keep essential content inside this box.
export const SAFE = {top: 230, bottom: 1920 - 400, left: 70, right: 1080 - 150};

const FONT_FILES: {family: string; file: string; weight?: string}[] = [
  {family: 'Anton', file: 'Anton-Regular.ttf', weight: '400'},
  {family: 'Montserrat', file: 'Montserrat-Variable.ttf', weight: '100 900'},
  {family: 'Inter', file: 'Inter-Variable.ttf', weight: '100 900'},
  {family: 'Poppins', file: 'Poppins-Medium.ttf', weight: '500'},
  {family: 'Poppins', file: 'Poppins-Bold.ttf', weight: '700'},
  {family: 'Poppins', file: 'Poppins-ExtraBold.ttf', weight: '800'},
  {family: 'Poppins', file: 'Poppins-Black.ttf', weight: '900'},
  {family: 'Teko', file: 'Teko-Variable.ttf', weight: '300 700'},
  {family: 'Noto Sans Devanagari', file: 'NotoSansDevanagari-Variable.ttf', weight: '100 900'},
  {family: 'Noto Sans Bengali', file: 'NotoSansBengali-Variable.ttf', weight: '100 900'},
  {family: 'Noto Sans Tamil', file: 'NotoSansTamil-Variable.ttf', weight: '100 900'},
  {family: 'Noto Sans Telugu', file: 'NotoSansTelugu-Variable.ttf', weight: '100 900'},
  {family: 'Noto Sans Gujarati', file: 'NotoSansGujarati-Variable.ttf', weight: '100 900'},
  {family: 'Noto Sans Kannada', file: 'NotoSansKannada-Variable.ttf', weight: '100 900'},
  {family: 'Noto Sans Malayalam', file: 'NotoSansMalayalam-Variable.ttf', weight: '100 900'},
  {family: 'Noto Sans Gurmukhi', file: 'NotoSansGurmukhi-Variable.ttf', weight: '100 900'},
];

let fontsPromise: Promise<void> | null = null;

export const ensureFonts = (): void => {
  if (fontsPromise) return;
  const handle = delayRender('Loading fonts');
  fontsPromise = Promise.all(
    FONT_FILES.map((f) =>
      loadFont({family: f.family, url: staticFile(`fonts/${f.file}`), weight: f.weight}).catch(() => undefined),
    ),
  ).then(() => {
    continueRender(handle);
  });
};

export const fontStack = (family: string, brand: Brand) =>
  `"${family}", "${brand.fonts.body}", "Inter", "Noto Sans Devanagari", sans-serif`;

export const mediaUrl = (m: Media | null | undefined, base: string): string => {
  if (!m) return '';
  if (/^https?:\/\//.test(m.src)) return m.src;
  return `${base.replace(/\/$/, '')}/${m.src.replace(/^\//, '')}`;
};

export const hexToRgba = (hex: string, a: number) => {
  const h = hex.replace('#', '');
  const n = parseInt(h.length === 3 ? h.split('').map((c) => c + c).join('') : h, 16);
  return `rgba(${(n >> 16) & 255}, ${(n >> 8) & 255}, ${n & 255}, ${a})`;
};

export const formatNumber = (value: number, decimals = 0, locale = 'en-US') =>
  new Intl.NumberFormat(locale, {minimumFractionDigits: decimals, maximumFractionDigits: decimals}).format(value);

export const upper = (s: string, brand: Brand) => (brand.subtitles.case === 'upper' && brand.script === 'latin' ? s.toUpperCase() : s);
