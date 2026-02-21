# SENTRY UI Design System

## Design Language: LRI-Labs Enterprise Standard

SENTRY follows the LRI-Labs design system used across internal JPMorgan CT tools. This is NOT a generic Material/Ant Design UI — it has a specific visual identity that MUST be replicated exactly.

**THE CANONICAL VISUAL REFERENCE is `@docs/ui-reference.html`** — open this file in a browser before building ANY UI component. Every color, spacing, font choice, and component pattern is demonstrated there.

## Design Tokens

### Colors
```css
:root {
  /* Core palette */
  --header-bg: #1a2e3b;          /* Dark blue-grey header */
  --header-text: #ffffff;
  --accent-teal: #2fb5a0;         /* PRIMARY accent — used for active states, links, CTAs */
  --accent-teal-hover: #28a08d;
  --accent-teal-dim: rgba(47, 181, 160, 0.12);     /* Teal backgrounds */
  --accent-teal-border: rgba(47, 181, 160, 0.3);

  /* Surfaces */
  --body-bg: #f4f6f8;             /* Page background */
  --card-bg: #ffffff;             /* Card/panel background */

  /* Text hierarchy */
  --text-primary: #1a2e3b;        /* Headers, important values */
  --text-secondary: #5a6b7a;      /* Body text, descriptions */
  --text-muted: #8a96a3;          /* Labels, captions, timestamps */

  /* Borders */
  --border-color: #e2e8ee;        /* Card borders, table borders */
  --border-light: #f0f2f5;        /* Row separators, subtle dividers */

  /* Status colors — EXACT values, do not substitute */
  --success: #2fb5a0;             /* Same as accent teal — intentional */
  --success-bg: rgba(47, 181, 160, 0.08);
  --error: #e74c5e;
  --error-bg: rgba(231, 76, 94, 0.08);
  --warning: #f0a830;
  --warning-bg: rgba(240, 168, 48, 0.08);
  --running: #4a90d9;
  --running-bg: rgba(74, 144, 217, 0.08);
  --cancelled: #8a96a3;

  /* Shadows */
  --shadow-sm: 0 1px 3px rgba(26, 46, 59, 0.06);
  --shadow-md: 0 2px 8px rgba(26, 46, 59, 0.08);

  /* Border radius */
  --radius-sm: 4px;
  --radius-md: 6px;
  --radius-lg: 8px;
}
```

### Typography
```css
/* Primary font: Source Sans 3 (formerly Source Sans Pro) */
font-family: 'Source Sans 3', -apple-system, BlinkMacSystemFont, sans-serif;

/* Monospace (for data values, timestamps, IDs): JetBrains Mono */
font-family: 'JetBrains Mono', monospace;

/* Font sizes */
--font-xs: 10.5px;    /* Hints, micro-labels */
--font-sm: 11.5px;    /* Table headers, badges, secondary info */
--font-body: 13px;    /* Default body text, table cells */
--font-md: 13.5px;    /* Section titles, nav items */
--font-lg: 14px;      /* Chat title, panel headers */
--font-xl: 18px;      /* Page title */
--font-xxl: 20px;     /* Brand name only */
--font-metric: 26px;  /* Summary card big numbers */
```

## Component Specifications

### Header Bar
- Height: 52px, fixed top
- Background: var(--header-bg)
- Brand: "SENTRY" in 20px, font-weight 700, letter-spacing 1.5px, white
- Nav items: 13.5px, weight 500, horizontally centered
- Active nav: white text + 3px teal underbar (border-radius 3px 3px 0 0)
- Inactive nav: 60% white opacity + 2px dim teal underbar
- Right side: PROD badge (teal on teal-dim bg) + connection dot (animated pulse) + icon buttons

### Summary Cards
- Grid: 5 columns, 14px gap
- Card: white bg, 1px border, border-radius 6px, shadow-sm
- Padding: 14px 16px
- Label: 11.5px uppercase, weight 500, muted color, letter-spacing 0.4px
- Value: 26px, weight 700, colored by status type
- Sub-text: 11.5px, muted

### Data Table
- Full-width within section card
- Header row: #fafbfc background, 12px uppercase, weight 600, muted color
- Row hover: rgba(47, 181, 160, 0.03) — very subtle teal tint
- Row border: var(--border-light) — barely visible
- Cell padding: 10px 14px
- Expand arrow: 14px SVG chevron-right, rotates 90° on expand
- Batch names: teal colored links (var(--accent-teal)), weight 500
- Timestamps: JetBrains Mono, 12px, secondary color

### Status Badges
- Inline-flex, small (12px, 3px 10px padding, border-radius 3px)
- Include 6px status dot before text
- SUCCESS: teal text on teal-bg
- FAILED: red text on red-bg
- RUNNING: blue text on blue-bg (dot has pulse animation)
- WARNING/WAITING: orange text on orange-bg
- CANCELLED: grey text on grey-bg

### Prelim/Final Indicators
- Two rows stacked vertically, 3px gap
- Each row: label (11.5px, muted, 42px width) + 7px dot
- Dot colors: green=done, blue=running(animated), red=failed, grey=not started, orange=warning

### Progress Bar
- Track: 5px height, var(--border-light), border-radius 3px
- Fill: colored by status (success=teal, running=blue, error=red)
- Text: 11.5px weight 600 next to bar ("4/6")
- Max width: 120px

### Expanded Row (Drill-down)
- Background: #f8fafb
- Inner table: full border, #f0f3f5 header bg
- Monospace font for dataset IDs, DAG IDs
- Sequence badge: 22px circle, teal text on teal-dim bg
- Quick action buttons below: small pills (11px, border, border-radius 3px)

### Chat Panel (Right Side)
- Width: 420px, white background, left border
- Header: 14px title, connection status with pulse dot
- Context bar: #f8fafb background, teal tags for active filters
- Messages: assistant=left-aligned #f4f6f8 bubble, user=right-aligned header-bg bubble
- Tool call display: bordered cards with ⚡ icon, monospace, collapsible
- Data cards in chat: white bg, bordered, with severity indicator (left border colored)
- Suggested queries: teal chips (11.5px, rounded pill shape, teal border)
- Input: textarea in #f4f6f8 box, teal focus ring, send button (teal bg)
- Hint line: 10.5px muted with kbd-styled shortcut hints

### Sequence Badge
- 22px × 22px circle
- Teal text on teal-dim background
- 11px font, weight 600
- Shows sequence order number (0, 1, 2...)

## Layout

### Split Panel Design
- Left: Dashboard panel (flex: 1, scrollable)
- Right: Chat panel (fixed 420px width)
- Resize handle between panels (4px, turns teal on hover)
- Both panels are always visible — SREs need to see status while chatting

### Responsive Behavior
- Minimum viewport: 1280px wide
- Below 1280px: chat panel collapses to overlay/drawer
- Tables: horizontal scroll if needed, headers sticky

## Animation
- Status dot pulse: 2s infinite (opacity 1→0.5→1)
- Thinking dots: 1.2s infinite, staggered (0.2s delay between dots)
- Message entry: 0.25s ease-out (opacity + translateY)
- Expand/collapse: 0.2s transform rotate on chevron
- Hover transitions: 0.15s on buttons, 0.1s on table rows

## Icons
- Use inline SVGs, 14-16px, stroke-width 2
- Color inherits from parent (currentColor)
- Icons: chevron-right (expand), calendar (date picker), refresh-cw (refresh), filter/funnel (table filter), bell (notifications), settings (gear), plus (new chat), clock (history), maximize (expand panel), send (paper plane)
