# Design QA

## Comparison Target

- Source visual truth: `C:\Users\user\AppData\Local\Temp\codex-clipboard-5383207a-8636-4a28-95ba-19982f244cf8.png`
- Source pixels: 975 × 808
- Source CSS size and density: not provided; treated as a 975 × 808 desktop reference at unknown density
- Implementation route/state: authenticated `/#/account`, populated API Key list, default Bearer Token tab, password fields empty
- Implementation screenshot: unavailable
- Implementation viewport, CSS size, and density: unavailable

## Evidence Status

The source image was opened and inspected. A browser-rendered implementation image could not be captured because the workspace instruction explicitly prohibits starting the frontend project, and no authenticated rendered artifact was supplied. Therefore a normalized side-by-side visual comparison was not possible.

Static implementation checks completed, but they are not substitutes for visual evidence:

- Desktop structure follows the reference: wide API Key column on the left, narrow password column on the right, and API usage help directly below the table.
- Responsive container rules cover single-column, horizontally scrollable table, and mobile card-table states.
- Typography, spacing, border, color, icon, copy, focus, empty, error, and interaction states were reviewed in source.
- No raster imagery or custom visual assets are present in the reference; project-standard icon components are used.
- API Key values remain prefix-only in the table; full secrets remain one-time reveal values after creation or rotation.
- Frontend tests: 27 files and 138 tests passed.
- Production build: passed.

## Full-view Comparison Evidence

Blocked: no implementation screenshot exists at the same viewport and authenticated state as the source.

## Focused Region Comparison Evidence

Blocked for the API Key table, password form, and API usage card because no implementation screenshot exists. Source-level inspection alone cannot confirm font rendering, exact track proportions, wrapping, control height, overflow, or visual rhythm.

## Findings

- [P1] Browser-rendered fidelity is unverified.
  - Location: full `/#/account` page.
  - Evidence: the 975 × 808 source is available, but there is no implementation capture.
  - Impact: exact visual fidelity and responsive behavior cannot be certified from code and jsdom tests alone.
  - Fix: with the user's permission, open an already authenticated local frontend or start the normal frontend preview, capture `/#/account` at the matching desktop viewport plus one narrow viewport, and compare both images together.

## Comparison History

- Pass 1: source opened; implementation capture blocked by the no-start workspace instruction. No visual fixes can be evidence-validated in this pass.
- Static review: fixed a visible table-caption leak, bound the table overflow breakpoint to the API panel itself, corrected mobile row-header layout, tightened form/button accessibility, protected password/API Key mutations from credential and cross-session races, and prevented navigation from discarding a one-time Key response. These fixes remain source-verified only because a rendered comparison is unavailable.

## Implementation Checklist

- Capture the authenticated desktop implementation at a viewport that yields a 975 × 808 account content comparison.
- Capture a narrow state below the 560px account-container breakpoint.
- Compare full view and focused table/form regions with the source in the same visual input.
- Fix any P0/P1/P2 mismatch and repeat the comparison.

## Follow-up Polish

- Confirm the browser's Chinese font metrics and API table column wrapping against the source once rendered evidence is available.

final result: blocked
