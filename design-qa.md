# Design QA — 首页方案 1

- Source visual truth: `/Users/xufeng/.codex/generated_images/01a1a22d-d9dd-7000-af7d-c161596e3801/exec-691266f4-696d-43e8-bfe6-bf82a8795d13.png`
- Implementation: `http://127.0.0.1:4173/`，`public/app.js` + `public/styles.css`
- Implementation screenshot: Codex in-app Browser tab 12 inline capture, 2026-11-15（浏览器未暴露本地截图路径）
- Viewport: app content `390 × 844` CSS px
- Source pixels: `852 × 1846`; compared after normalizing to the `390 × 844` app-content ratio
- Implementation pixels: browser capture contains the unscaled `390 × 844` app shell inside the desktop preview canvas
- State: empty dining-session home; light theme

## Full-view comparison evidence

The source and implementation were opened in the same review pass. Both use the same four-part hierarchy: compact brand header, two-line headline, dominant circular camera action with album alternative, then a divided optional Xiaohongshu attachment row. The implemented page removes the former descriptive paragraph, dual cards, submit arrow, privacy paragraph, and visible screenshot fallback.

## Focused region comparison evidence

- Primary action: implementation uses a 224 px black circle, centered camera icon, and “拍菜单”, matching the source's dominant shape and contrast.
- Guide context: the home screen contains no guide control. After one or more menu images are selected, the confirmation sheet explains the benefit and exposes an optional Xiaohongshu-link input beside the staged menu thumbnails.
- Link input: verified directly in the menu-confirmation sheet; it is optional, explains the matching benefit, and does not add another entry step.
- Failure state: verified with a rejected non-Xiaohongshu URL; only after failure does the “上传攻略截图” fallback sheet appear.

## Required fidelity surfaces

- Fonts and typography: system `SF Pro Text` / `PingFang SC` stack, heavy 46 px display headline, compact supporting labels; hierarchy and wrapping match the source.
- Spacing and layout rhythm: header, hero, circular action, album link, divider, and attachment row align to the source's generous vertical rhythm without overflow.
- Colors and visual tokens: off-white `#fbfbf8`, near-black `#111211`, warm gray secondary text, fine gray divider, and restrained lime accent match the selected direction.
- Image and icon fidelity: the source contains no raster imagery. Standard Phosphor camera and link icons are used; no CSS-drawn or placeholder artwork is present.
- Copy and content: visible home copy matches the selected design; screenshot fallback copy is absent from the initial page and appears only in its error state.

## Findings

No actionable P0, P1, or P2 differences remain.

## Comparison history

- Initial implementation capture: source hierarchy and proportions matched; no blocking mismatch found.
- Interaction capture: link input and failure-only screenshot fallback behaved as intended; no visual correction was required.

## Follow-up polish

- P3: evaluate the large circle's pressed-state feedback on a physical phone after device testing.

final result: passed
