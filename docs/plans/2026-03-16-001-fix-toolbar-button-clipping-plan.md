---
title: "fix: Toolbar buttons clip at narrow viewports"
type: fix
status: active
date: 2026-03-16
---

# fix: Toolbar buttons clip at narrow viewports

## Overview

The left panel toolbar row ("Enrich Document", "Clear", "Show Thinking", "Debug Mode") gets clipped at narrower browser widths or higher zoom levels. The "Debug Mode" button is cut off and unreadable/unclickable. The row should wrap gracefully instead.

## Root Cause

Three CSS properties combine to cause the clipping in `frontend/index.html`:

1. **No `flex-wrap`** on the inline button container div (line ~2548) — defaults to `nowrap`
2. **`flex-shrink: 0`** on `.panel-header button` (line ~320) — buttons refuse to shrink
3. **`overflow: hidden`** on `.panel` (line ~214) — clips overflowing content

## Proposed Solution

Add `flex-wrap: wrap` at two levels so both the panel header row and the button group within it can wrap gracefully.

### Change 1 — `.panel-header` CSS (line ~304)

Add `flex-wrap: wrap` and a small `gap` so the h2 label and button group can stack vertically at narrow widths.

```css
/* Before */
.panel-header {
  padding: 10px 16px;
  background: var(--surface);
  border-bottom: 1px solid var(--border);
  display: flex;
  justify-content: space-between;
  align-items: center;
}

/* After */
.panel-header {
  padding: 10px 16px;
  background: var(--surface);
  border-bottom: 1px solid var(--border);
  display: flex;
  justify-content: space-between;
  align-items: center;
  flex-wrap: wrap;
  gap: 6px;
}
```

### Change 2 — Button container inline style (line ~2548)

Add `flex-wrap:wrap` so buttons within the group wrap to a second row.

```html
<!-- Before -->
<div style="display:flex;gap:8px;align-items:center">

<!-- After -->
<div style="display:flex;gap:8px;align-items:center;flex-wrap:wrap">
```

## Acceptance Criteria

- [ ] At full width (~1400px+), toolbar displays on one line (no visual change)
- [ ] At ~900px width or 125%+ zoom, buttons wrap to a second row instead of clipping
- [ ] "Debug Mode" button is always fully visible and clickable
- [ ] No layout shifts or visual regressions at any viewport size

## Verification

1. Open `frontend/index.html` at `http://localhost:8732`
2. Full width: confirm toolbar looks identical to current behavior
3. Narrow browser to ~900px or zoom to 125%+: confirm buttons wrap, none clipped
4. Test at very narrow widths (~700px): confirm graceful stacking, no overflow
