# 食途 Design System

## 1. Project overview

- **Product:** 食途，法国餐厅现场点餐助手。
- **Surface profile:** Redesign + App/Product UI + mobile-web guidance.
- **Platform:** Mobile-first web/PWA; desktop only provides a centered preview shell.
- **Target users:** 已经坐在法国餐厅里、需要边扫菜单边决策的中国旅行者。
- **Main design goal:** 让拍摄、翻译、攻略匹配、追问和勾选像使用同一份可批注菜单，而不是在多个 AI 功能页之间跳转。

## 2. Brand direction

- **Visual style:** Rational, calm and workmanlike; compact without feeling crowded.
- **Mood:** 桌边正在使用的工具，而非法式餐厅宣传页。
- **Personality:** Rational-human.
- **Concept:** “桌边批注菜单”——用紧凑的单列菜单、中性纸面、荧光攻略标记和明确勾选反馈，表达一份被逐页扫描和持续编辑的工作副本。
- **Adversarial verdict:** 隐去品牌名后，“攻略标记 + 法文原名 + 原图定位 + 持续点菜单”仍使它不同于通用翻译或外卖 App。初稿弱点是菜品行仍偏高；已将攻略 badge 并入菜名并压缩垂直间距。
- **References:**
  - [Google Lens](https://search.google/intl/en-GB/ways-to-search/lens/): 借用 camera-first 的主动作和“图像是来源”的交互逻辑。
  - [Google Translate image translation](https://support.google.com/translate/answer/6142483): 借用拍摄与导入两种明确输入路径。
  - [Apple Notes checklists](https://support.apple.com/en-gb/102296): 借用平面列表、稳定对齐和明确勾选反馈。
  - [Baymard food-ordering research](https://baymard.com/research/online-food-delivery): 借用选菜过程中持续可见的当前订单和总价。
- **Voice:** 直接、具体、不拟人化 AI。CTA 使用“拍菜单”、“开始扫菜单”、“加入”等动词。加载与错误文案说明正在做什么、用户如何继续。

## 3. Color system

| Role | Color | Hex | Usage |
|---|---|---|---|
| Dominant | cool neutral background | `#EEF0ED` | browser background |
| Dominant canvas | paper canvas | `#F8F9F6` | application base |
| Secondary | clean surface | `#FEFEFC` | grouped lists and floating sheets |
| Secondary muted | control surface | `#E8EBE7` | secondary actions and source strip |
| Primary text | ink | `#171B18` | headings and body |
| Secondary text | graphite | `#505852` | explanations and metadata |
| Tertiary text | soft graphite | `#68726B` | captions; verified 4.72:1 on canvas |
| Primary action | deep ink green | `#203C33` | primary buttons and selected controls |
| Pressed action | dark ink green | `#152D26` | pressed/hover action |
| Selection surface | pale ink | `#E4EEE9` | selected dish background |
| Guide marker | highlighter | `#E6ED72` | guide match label only |
| Guide surface | highlighter wash | `#F5F7D9` | guide-related row background |
| Divider | neutral line | `#D4D9D4` | list and top-bar dividers |
| Focus | focus green | `#376E5D` | focus-visible outline |
| Warning | warning ink | `#745600` | model connection warning |
| Warning surface | warning wash | `#F2EAD1` | warning background |
| Danger | source red | `#9F3838` | original-image bounding box |

Approved translucent derivatives are `rgba(254,254,252,.14)` for action overlays, `rgba(159,56,56,.12)` for source highlighting, `rgba(23,27,24,.48)` for the sheet scrim and `rgba(238,240,237,.72)` for the recognition scrim. Approved shadows are `0 2px 14px rgba(31,42,36,.06)` and `0 12px 36px rgba(31,42,36,.12)`.

Use neutral canvas for roughly 60%, white/muted grouped surfaces for 30%, and action/highlighter colors for at most 10%. No dark mode in MVP. Borders are allowed only as thin list/input dividers, not as elevation; grouped surfaces use background contrast and one quiet shadow.

## 4. Typography system

- **Personality:** rational-human.
- **Family:** `PingFang SC`, `Hiragino Sans GB`, `Microsoft YaHei`, `system-ui`, sans-serif. The Latin home wordmark alone uses `Iowan Old Style` or a serif fallback.
- **Why:** system Chinese sans renders reliably on a traveller's phone and keeps Chinese, French names, prices and punctuation visually aligned; the small English wordmark adds brand character without changing reading surfaces.
- **Scale:** home display `39–42px`; h1 `clamp(24px, 6vw, 28px)`; h2 `20px`; h3 `17px`; body `16px`; body-sm `14px`; caption `13px`; buttons `14–16px`.
- **Line height:** headings 1.12–1.35; body 1.5–1.65.
- **Numbers:** prices and totals use tabular numerals.
- **Responsive:** display and h1 use fluid scaling; labels may wrap rather than truncate meaning.

## 5. Layout system

- **Container:** full-width on phones; desktop preview is deliberately fixed at `375px` to expose phone-layout defects during review.
- **Gutter:** `16px`; narrow-phone gutter `12px`.
- **Spacing:** `4 / 8 / 12 / 16 / 24 / 32px`.
- **Canonical flow:** photograph or batch-select menus → confirm pages and optionally attach a Xiaohongshu link → scanned menu pages with guide matches → persistent selection/chat bar → French order.
- **Primary goal:** scan a menu page. Each screen exposes one dominant action.
- **Mobile modality:** original-image and chat tasks use bottom sheets; persistent bottom controls reserve `116px` page padding plus safe-area inset.
- **List-to-detail:** dish list opens original-image position in a sheet; closing returns to the same menu state.
- **Session boundary:** the dining-screen back action ends and clears the current session immediately; reopening always starts from a clean home screen rather than resuming stale data.
- **Hero:** a result-led task statement and one non-interactive preview show the transition from a photographed menu to a selectable dish. A centered circular camera control is the dominant home action; choosing from the album is a quiet text action below it. Optional guide input appears after menu selection.
- **Horizontal rails:** none in MVP; menu page controls wrap instead of using raw horizontal scrolling.
- **Breakpoints:** phone `320–460px`; centered `375px` device preview from `700px`.
- **Alignment:** top bar, headings, summaries, tabs and grouped lists share the same 16px grid.

## 6. Component system

- **Base:** native HTML/CSS/JavaScript; no external component library.
- **Buttons:** primary ink-filled, secondary muted, ghost text, text action, and 44px icon-close variant. All include hover, focus-visible, pressed and disabled rules.
- **Grouped list:** one raised surface containing flat rows divided by hairlines; individual dishes are not separate cards.
- **Guide marker:** compact text signal in the decision line; explicit source rating is preserved, while recommendation, caution and mention use distinct semantic text colors.
- **Top bar:** fixed placement across all stages; text wordmark, product context and connection status.
- **Forms:** native file labels, a labelled optional guide-link input in the pre-scan confirmation sheet, and a labelled chat input.
- **Sheets:** source location, guide evidence, add-page and chat appear from the bottom with a visible close button. Guide quotes never expand inside the dense menu list.
- **Feedback:** inline model warning, blocking recognition feedback and toast result.

## 7. Card and section style

- **Style:** grouped flat lists, not card-per-item.
- **Radius:** `6 / 10 / 14px`.
- **Elevation:** `0 2px 14px rgba(31,42,36,.06)` for grouped surfaces; `0 12px 36px rgba(31,42,36,.12)` only for floating sheets/desktop shell.
- **Gradients/glass:** none.
- **Rule:** page base → grouped surface → bottom sheet. Never nest elevated cards.

## 8. Icon system

- **Library:** none for MVP. Text labels carry primary meaning.
- **Custom marks:** CSS scan-frame and plain arrows/close glyphs only; unfamiliar icon-only controls require `aria-label`.
- **Rule:** no sparkle, magic, emoji or mixed icon families.

## 9. Image and asset rules

- **Logo:** text wordmark; no generated logo asset.
- **User images:** menu and guide screenshots are the only prominent imagery.
- **Crop:** guide thumbnail uses `92×68px` top crop; original menu uses contain and preserves the full page.
- **Radius:** `6–10px` for thumbnails/source view.
- **Treatment:** never decorate, recolor or replace uploaded evidence.

## 10. Animation and interaction system

- **Library:** CSS only.
- **Durations:** `150ms` press/hover; `220ms` sheet and toast.
- **Properties:** transform and opacity for motion; background changes are immediate state feedback.
- **Pressed:** controls scale to `.98–.99`.
- **Focus:** 3px `#376E5D` focus-visible ring with 3px offset.
- **Async:** current surface is blocked and a centered “正在识别菜单…” status appears immediately; success renders the page and errors use a toast.
- **States:** start, empty menu, recognition loading, recoverable toast error, guide matches, selected/unselected dishes and empty order are all represented.
- **Reduced motion:** all transitions and animations turn off under `prefers-reduced-motion`.
- **Performance:** native CSS/JS, no font or component payload, image dimensions/aspect reserved where rendered, uploaded images resized client-side before sending. CWV targets are pursued through the nine levers but are not yet lab-measured.

## 11. Accessibility rules

- Body/supporting text is at least 4.5:1. Verified ratios: text/canvas `16.47:1`; secondary/canvas `6.95:1`; tertiary/canvas `4.72:1`; action/surface `11.85:1`; marker/text `13.86:1`; focus/canvas `5.60:1`.
- All primary controls are at least 44px high; the start actions are 82px and bottom actions 54px.
- Every interactive element receives a visible `:focus-visible` state; mouse focus does not flash a ring.
- A skip link targets the main application region.
- Text, label or checkmark accompanies every colored status.
- `prefers-reduced-motion` and `forced-colors` receive explicit adaptations.
- Chinese text may scale and wrap; critical labels are not ellipsized.

## 12. Anti-AI-slop rules

- Only the colors in section 3 are approved; no raw pure black/white.
- No decorative serif, travel-poster composition, French tricolor, cream-and-burgundy category reflex, feature-chip row, sparkle icon, gradient text, glass or card-per-feature layout.
- Eyebrows are replaced by factual step labels. Guide badges express real source status.
- Product-specific exception: the 13px caption step is allowed for compact metadata while all reading/explanation copy remains 16px.
- Concept-test verdict and corrected density weakness are recorded in section 2.

## 13. Future page instructions

Future pages must reuse these colors, typography, spacing, grouped-list structure, action hierarchy, marker semantics and bottom-sheet behavior. New visual styles require explicit product justification and a design-system update.

## 14. Update policy

Any change to tokens, components, typography, states, image treatment or motion must update this file in the same change so the documentation remains identical to the live UI.
