// SVG 图标库。统一 24×24 viewBox，stroke 风格，对齐设计稿 ICONS。
// 用 react-native-svg 渲染。

import Svg, { Circle, Path, Rect } from "react-native-svg";

const SW = 1.8; // stroke-width

const ICON_PATHS: Record<string, React.ReactNode> = {
  home: (
    <>
      <Path d="M3 11.5 12 4l9 7.5" />
      <Path d="M5.5 10.5V20h13v-9.5M9 20v-6h6v6" />
    </>
  ),
  chat: (
    <>
      <Path d="M20 14a4 4 0 0 1-4 4H8l-5 3V7a4 4 0 0 1 4-4h9a4 4 0 0 1 4 4z" />
      <Path d="M8 9h8M8 13h5" />
    </>
  ),
  note: (
    <>
      <Path d="M6 3h9l3 3v15H6z" />
      <Path d="M14 3v4h4M9 11h6M9 15h6" />
    </>
  ),
  graph: (
    <>
      <Circle cx="12" cy="5" r="2.5" />
      <Circle cx="5" cy="17" r="2.5" />
      <Circle cx="19" cy="17" r="2.5" />
      <Path d="m10.8 7.2-4.5 7.6m6.9-7.6 4.5 7.6M7.5 17h9" />
    </>
  ),
  settings: (
    <>
      <Circle cx="12" cy="12" r="3" />
      <Path d="M19.4 15a1.7 1.7 0 0 0 .3 1.9l.1.1-2.8 2.8-.1-.1a1.7 1.7 0 0 0-1.9-.3 1.7 1.7 0 0 0-1 1.6v.2h-4V21a1.7 1.7 0 0 0-1-1.6 1.7 1.7 0 0 0-1.9.3l-.1.1L4.2 17l.1-.1a1.7 1.7 0 0 0 .3-1.9A1.7 1.7 0 0 0 3 14H2.8v-4H3a1.7 1.7 0 0 0 1.6-1 1.7 1.7 0 0 0-.3-1.9L4.2 7 7 4.2l.1.1A1.7 1.7 0 0 0 9 4.6a1.7 1.7 0 0 0 1-1.6v-.2h4V3a1.7 1.7 0 0 0 1 1.6 1.7 1.7 0 0 0 1.9-.3l.1-.1L19.8 7l-.1.1a1.7 1.7 0 0 0-.3 1.9 1.7 1.7 0 0 0 1.6 1h.2v4H21a1.7 1.7 0 0 0-1.6 1z" />
    </>
  ),
  search: (
    <>
      <Circle cx="10.8" cy="10.8" r="6.8" />
      <Path d="m16 16 5 5" />
    </>
  ),
  mic: (
    <>
      <Rect x="9" y="3" width="6" height="12" rx="3" />
      <Path d="M6 11a6 6 0 0 0 12 0M12 17v4" />
    </>
  ),
  plus: <Path d="M12 5v14M5 12h14" />,
  back: <Path d="m15 18-6-6 6-6" />,
  more: (
    <>
      <Circle cx="5" cy="12" r="1" />
      <Circle cx="12" cy="12" r="1" />
      <Circle cx="19" cy="12" r="1" />
    </>
  ),
  send: <Path d="m4 4 17 8-17 8 3-8zM7 12h14" />,
  close: <Path d="M18 6 6 18M6 6l12 12" />,
  check: <Path d="M20 6 9 17l-5-5" />,
  clock: (
    <>
      <Circle cx="12" cy="12" r="10" />
      <Path d="M12 6v6l4 2" />
    </>
  ),
  logOut: <Path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4M16 17l5-5-5-5M21 12H9" />,
  alertCircle: (
    <>
      <Circle cx="12" cy="12" r="10" />
      <Path d="M12 8v4M12 16h.01" />
    </>
  ),
  file: (
    <>
      <Path d="M6 3h9l3 3v15H6z" />
      <Path d="M14 3v4h4" />
    </>
  ),
};

export interface IconProps {
  name: string;
  size?: number;
  color?: string;
}

export function Icon({ name, size = 21, color = "#2b2722" }: IconProps) {
  const paths = ICON_PATHS[name];
  if (!paths) return null;
  return (
    <Svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke={color}
      strokeWidth={SW}
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      {paths}
    </Svg>
  );
}

export type IconName = keyof typeof ICON_PATHS;
