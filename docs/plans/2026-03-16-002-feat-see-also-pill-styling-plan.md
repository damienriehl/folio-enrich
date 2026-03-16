---
title: feat: Style See Also links as translation-style pills
type: feat
status: active
date: 2026-03-16
---

# feat: Style "See Also" links as translation-style pills

## Context

The FOLIO concept detail panel currently renders "See Also" links (e.g., "Landlord Tenant Law", "Lessee") as plain comma-separated blue hyperlinks. The user wants them styled as rounded gray pills matching the translation pills (flag + label pills). This also eliminates a duplication issue: "See Also" data currently renders in two places — inline as plain links AND in a separate "Related" section as concept pills with purple dots.

## Proposed Solution

Convert the inline "See Also" rendering to use translation-style pills (gray rounded, no dot), remove the duplicate dedicated `renderDetailRelated` section, and clean up unused CSS/HTML.

## Changes (3 edits, 1 file)

All changes in `frontend/index.html`:

### 1. Replace inline "See Also" plain links with pill-style rendering (~line 7606-7611)

**Before:**
```javascript
if (detail.related && detail.related.length) {
  const relLinks = detail.related.map(r =>
    `<a href="#" class="detail-related-link" onclick="...">${escapeHtml(r.label)}</a>`
  ).join(', ');
  html += `<div class="detail-meta-field"><strong>See Also:</strong> ${relLinks}</div>`;
}
```

**After:**
```javascript
if (detail.related && detail.related.length) {
  const pills = detail.related.map(r =>
    `<span class="detail-trans-pill detail-seealso-pill" onclick="loadConceptDetail('${escapeAttr(r.iri_hash)}')">${escapeHtml(r.label)}</span>`
  ).join('');
  html += `<div class="detail-translations">
    <div class="detail-trans-header"><strong>See Also</strong><span class="detail-trans-count">(${detail.related.length})</span></div>
    <div class="detail-trans-pills">${pills}</div>
  </div>`;
}
```

- Reuses the existing `.detail-translations`, `.detail-trans-header`, `.detail-trans-pills`, and `.detail-trans-pill` CSS classes
- Adds `.detail-seealso-pill` modifier for cursor:pointer styling (since these are clickable navigation, unlike static translation labels)
- Matches the translation section structure: header row with count + wrapped pill container

### 2. Add `.detail-seealso-pill` CSS (~after line 591)

```css
.detail-seealso-pill { cursor: pointer; }
.detail-seealso-pill:hover { background: rgba(59,100,224,0.08); border-color: #3b64e0; color: #3b64e0; }
```

### 3. Remove the duplicate `renderDetailRelated` function and its call

- **Delete** `renderDetailRelated()` function (lines 7897-7911)
- **Delete** the call `renderDetailRelated(detail)` at line 6611
- **Delete** unused CSS: `.detail-related-link` and `.detail-related-link:hover` (lines 595-596)
- **Optionally** remove or leave the `<div id="detailRelated">` container (line 2756) — it'll just be empty

## Files Modified

| File | Change |
|------|--------|
| `frontend/index.html:7606-7611` | Replace plain links with pill rendering |
| `frontend/index.html:~591` | Add `.detail-seealso-pill` CSS |
| `frontend/index.html:7897-7911` | Delete `renderDetailRelated()` |
| `frontend/index.html:6611` | Delete `renderDetailRelated(detail)` call |
| `frontend/index.html:595-596` | Delete `.detail-related-link` CSS |

## Verification

1. **Start dev server**: `cd backend && .venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8731 --reload`
2. **Open frontend**: http://localhost:8732
3. **Enrich a legal document** containing terms with "See Also" relationships (e.g., terms like "Tenant", "Landlord", "Lessee")
4. **Click an annotation** to open the concept detail panel
5. **Verify "See Also" pills**: Should appear as gray rounded pills matching translation pill style
6. **Verify click behavior**: Clicking a "See Also" pill should navigate to that concept's detail
7. **Verify no duplicate**: The old separate "Related" section should no longer appear
8. **Take a screenshot** to visually confirm the styling matches
