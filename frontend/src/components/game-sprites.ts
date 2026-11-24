// Pixel sprite catalogue — the SVG source for each food sprite lives both
// here (as a string, for the running app) and in `frontend/assets/games/
// sprites/*.svg` (as the human-readable source of truth, licensed and
// credited in `assets/games/CREDITS.md`). They are kept byte-identical by
// convention; the .svg files are the canonical copy for designers.
//
// Why not require() the .svg files directly: Metro doesn't understand
// `.svg` out of the box, and pulling in `react-native-svg-transformer` is
// more Metro-config churn than this one feature deserves. `react-native-svg`
// is already a project dependency, and `SvgXml` renders these inline.
export const spriteNames = [
  "apple",
  "carrot",
  "broccoli",
  "egg",
  "rice-bowl",
  "bread",
  "fish",
  "cheese",
  "water",
  "cookie",
  "salad",
] as const;

export type SpriteName = (typeof spriteNames)[number];

export const SPRITES: Record<SpriteName, string> = {
  apple: `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 16 16" shape-rendering="crispEdges">
    <rect x="8" y="2" width="1" height="2" fill="#5A3B21"/>
    <rect x="9" y="2" width="2" height="1" fill="#5FA85C"/>
    <rect x="10" y="3" width="1" height="1" fill="#3E7E3E"/>
    <rect x="5" y="5" width="2" height="1" fill="#F76A5B"/>
    <rect x="4" y="6" width="4" height="2" fill="#F76A5B"/>
    <rect x="3" y="8" width="6" height="3" fill="#D9412E"/>
    <rect x="4" y="11" width="4" height="2" fill="#A61F13"/>
    <rect x="7" y="5" width="3" height="1" fill="#D9412E"/>
    <rect x="8" y="6" width="4" height="2" fill="#D9412E"/>
    <rect x="9" y="8" width="4" height="3" fill="#A61F13"/>
    <rect x="8" y="11" width="4" height="2" fill="#6E140B"/>
    <rect x="5" y="7" width="1" height="1" fill="#FFC9BF"/>
  </svg>`,
  carrot: `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 16 16" shape-rendering="crispEdges">
    <rect x="6" y="1" width="1" height="3" fill="#3E7E3E"/>
    <rect x="7" y="0" width="2" height="4" fill="#5FA85C"/>
    <rect x="9" y="1" width="1" height="3" fill="#3E7E3E"/>
    <rect x="5" y="4" width="6" height="2" fill="#F38B2A"/>
    <rect x="5" y="6" width="6" height="2" fill="#E07820"/>
    <rect x="6" y="8" width="4" height="2" fill="#E07820"/>
    <rect x="6" y="10" width="4" height="2" fill="#B55615"/>
    <rect x="7" y="12" width="2" height="2" fill="#B55615"/>
    <rect x="7" y="14" width="1" height="1" fill="#78340A"/>
  </svg>`,
  broccoli: `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 16 16" shape-rendering="crispEdges">
    <rect x="4" y="2" width="3" height="2" fill="#3E7E3E"/>
    <rect x="9" y="2" width="3" height="2" fill="#3E7E3E"/>
    <rect x="3" y="4" width="4" height="2" fill="#5FA85C"/>
    <rect x="8" y="4" width="5" height="2" fill="#5FA85C"/>
    <rect x="2" y="6" width="12" height="2" fill="#3E7E3E"/>
    <rect x="3" y="8" width="10" height="1" fill="#2E6730"/>
    <rect x="5" y="3" width="1" height="1" fill="#9BD68F"/>
    <rect x="10" y="3" width="1" height="1" fill="#9BD68F"/>
    <rect x="6" y="9" width="4" height="2" fill="#B9D7A5"/>
    <rect x="7" y="11" width="2" height="3" fill="#B9D7A5"/>
  </svg>`,
  egg: `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 16 16" shape-rendering="crispEdges">
    <rect x="6" y="2" width="4" height="1" fill="#F3EAD1"/>
    <rect x="5" y="3" width="6" height="2" fill="#F3EAD1"/>
    <rect x="4" y="5" width="8" height="5" fill="#F3EAD1"/>
    <rect x="5" y="10" width="6" height="2" fill="#F3EAD1"/>
    <rect x="6" y="12" width="4" height="1" fill="#F3EAD1"/>
    <rect x="4" y="9" width="1" height="1" fill="#D8CFB3"/>
    <rect x="11" y="7" width="1" height="3" fill="#D8CFB3"/>
    <rect x="5" y="11" width="6" height="1" fill="#D8CFB3"/>
    <rect x="6" y="4" width="2" height="1" fill="#FFFFFF"/>
  </svg>`,
  "rice-bowl": `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 16 16" shape-rendering="crispEdges">
    <rect x="4" y="4" width="8" height="1" fill="#F8F3E6"/>
    <rect x="3" y="5" width="10" height="2" fill="#F8F3E6"/>
    <rect x="5" y="5" width="1" height="1" fill="#D8CFB3"/>
    <rect x="8" y="5" width="1" height="1" fill="#D8CFB3"/>
    <rect x="11" y="5" width="1" height="1" fill="#D8CFB3"/>
    <rect x="6" y="6" width="1" height="1" fill="#D8CFB3"/>
    <rect x="9" y="6" width="1" height="1" fill="#D8CFB3"/>
    <rect x="2" y="7" width="12" height="2" fill="#4A5EA6"/>
    <rect x="3" y="9" width="10" height="2" fill="#3A4D8A"/>
    <rect x="4" y="11" width="8" height="1" fill="#2E3F72"/>
    <rect x="5" y="12" width="6" height="1" fill="#1E2B5A"/>
    <rect x="3" y="8" width="2" height="1" fill="#7F94DD"/>
  </svg>`,
  bread: `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 16 16" shape-rendering="crispEdges">
    <rect x="3" y="4" width="10" height="1" fill="#B3741E"/>
    <rect x="2" y="5" width="12" height="2" fill="#D4902B"/>
    <rect x="2" y="7" width="12" height="4" fill="#E7B45C"/>
    <rect x="2" y="11" width="12" height="1" fill="#B3741E"/>
    <rect x="3" y="12" width="10" height="1" fill="#78340A"/>
    <rect x="5" y="5" width="1" height="2" fill="#78340A"/>
    <rect x="8" y="5" width="1" height="2" fill="#78340A"/>
    <rect x="11" y="5" width="1" height="2" fill="#78340A"/>
    <rect x="4" y="5" width="1" height="1" fill="#FFF2BE"/>
    <rect x="9" y="6" width="1" height="1" fill="#FFF2BE"/>
  </svg>`,
  fish: `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 16 16" shape-rendering="crispEdges">
    <rect x="12" y="4" width="1" height="2" fill="#4A5EA6"/>
    <rect x="13" y="3" width="1" height="4" fill="#4A5EA6"/>
    <rect x="12" y="10" width="1" height="2" fill="#4A5EA6"/>
    <rect x="13" y="9" width="1" height="4" fill="#4A5EA6"/>
    <rect x="3" y="6" width="10" height="4" fill="#6E85C9"/>
    <rect x="2" y="7" width="1" height="2" fill="#6E85C9"/>
    <rect x="6" y="5" width="3" height="1" fill="#4A5EA6"/>
    <rect x="4" y="7" width="1" height="1" fill="#101A16"/>
    <rect x="7" y="7" width="1" height="1" fill="#4A5EA6"/>
    <rect x="9" y="8" width="1" height="1" fill="#4A5EA6"/>
    <rect x="11" y="7" width="1" height="1" fill="#4A5EA6"/>
    <rect x="6" y="7" width="1" height="1" fill="#B0C1F2"/>
  </svg>`,
  cheese: `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 16 16" shape-rendering="crispEdges">
    <rect x="4" y="4" width="2" height="1" fill="#F0C049"/>
    <rect x="4" y="5" width="4" height="1" fill="#F0C049"/>
    <rect x="4" y="6" width="6" height="1" fill="#F0C049"/>
    <rect x="3" y="7" width="10" height="4" fill="#F7D166"/>
    <rect x="2" y="11" width="12" height="1" fill="#B3741E"/>
    <rect x="5" y="8" width="2" height="2" fill="#D4902B"/>
    <rect x="9" y="9" width="2" height="1" fill="#D4902B"/>
    <rect x="11" y="8" width="1" height="1" fill="#D4902B"/>
    <rect x="4" y="4" width="1" height="1" fill="#FFF2BE"/>
  </svg>`,
  water: `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 16 16" shape-rendering="crispEdges">
    <rect x="4" y="3" width="8" height="1" fill="#9FB7A6"/>
    <rect x="4" y="3" width="1" height="10" fill="#9FB7A6"/>
    <rect x="11" y="3" width="1" height="10" fill="#9FB7A6"/>
    <rect x="4" y="13" width="8" height="1" fill="#9FB7A6"/>
    <rect x="5" y="6" width="6" height="7" fill="#6E85C9"/>
    <rect x="5" y="5" width="6" height="1" fill="#8FA5DD"/>
    <rect x="6" y="7" width="1" height="3" fill="#B0C1F2"/>
  </svg>`,
  cookie: `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 16 16" shape-rendering="crispEdges">
    <rect x="5" y="3" width="6" height="1" fill="#B3741E"/>
    <rect x="4" y="4" width="8" height="1" fill="#D4902B"/>
    <rect x="3" y="5" width="10" height="6" fill="#D4902B"/>
    <rect x="4" y="11" width="8" height="1" fill="#B3741E"/>
    <rect x="5" y="12" width="6" height="1" fill="#78340A"/>
    <rect x="5" y="6" width="1" height="1" fill="#2A1A0E"/>
    <rect x="9" y="7" width="1" height="1" fill="#2A1A0E"/>
    <rect x="6" y="9" width="1" height="1" fill="#2A1A0E"/>
    <rect x="10" y="10" width="1" height="1" fill="#2A1A0E"/>
    <rect x="7" y="7" width="1" height="1" fill="#2A1A0E"/>
    <rect x="5" y="5" width="1" height="1" fill="#F7D166"/>
  </svg>`,
  salad: `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 16 16" shape-rendering="crispEdges">
    <rect x="2" y="8" width="12" height="2" fill="#D4902B"/>
    <rect x="3" y="10" width="10" height="2" fill="#B3741E"/>
    <rect x="4" y="12" width="8" height="1" fill="#78340A"/>
    <rect x="3" y="5" width="2" height="2" fill="#5FA85C"/>
    <rect x="5" y="4" width="2" height="2" fill="#3E7E3E"/>
    <rect x="7" y="5" width="2" height="2" fill="#5FA85C"/>
    <rect x="9" y="4" width="2" height="2" fill="#3E7E3E"/>
    <rect x="11" y="5" width="2" height="2" fill="#5FA85C"/>
    <rect x="4" y="7" width="8" height="1" fill="#3E7E3E"/>
    <rect x="6" y="6" width="2" height="1" fill="#D9412E"/>
    <rect x="10" y="7" width="2" height="1" fill="#F38B2A"/>
  </svg>`,
};
