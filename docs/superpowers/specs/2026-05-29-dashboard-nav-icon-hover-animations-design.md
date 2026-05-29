---
name: dashboard-nav-icon-hover-animations
description: Semantic per-icon hover animations on the DashboardNav tab bar. Icons animate once on hover; text labels remain unchanged.
metadata:
  type: project
---

# Dashboard Nav Icon Hover Animations

## Summary

Add semantic CSS hover animations to each tab icon in `DashboardNav.vue`. Animations play once per hover, do not loop, and do not affect text labels.

## Scope

**File:** `frontend/src/components/Layout/DashboardNav.vue`

No backend changes. No new dependencies.

## Animation Map

Each tab's icon (`lucide-vue-next` SVG) receives a unique animation that matches its semantic meaning:

| Tab ID | Icon | Keyframe | Rationale |
|--------|------|----------|-----------|
| workflows | Workflow | `icon-spin` (360° rotation) | Flow turning |
| schedules | CalendarClock | `icon-tick` (back-forth wiggle) | Clock ticking |
| templates | LayoutTemplate | `icon-pop` (scale 1→1.25→1) | Template opening |
| globalvariables | Variable | `icon-bounce` (translateY 0→-4px→0) | Value jumping |
| chat | MessageCircle | `icon-pulse` (scale 1→1.2→0.95→1) | Notification arriving |
| drive | HardDrive | `icon-spin` (360° rotation) | Disk spinning |
| datatable | Table2 | `icon-slide` (translateX 0→3px→0) | Row scrolling |
| credentials | Key | `icon-rotate` (rotate 0→20°→0) | Key turning |
| vectorstores | Database | `icon-pulse` (scale 1→1.2→0.95→1) | Data pulsing |
| mcp | Server | `icon-blink` (opacity 1→0.3→1) | Server LED blinking |
| traces | Activity | `icon-wiggle` (rotate -12°→12°→-6°→6°→0) | EKG waveform |
| analytics | BarChart3 | `icon-grow` (scaleY 0.7→1.1→1) | Bars rising |
| evals | FlaskConical | `icon-shake` (translateX -3px→3px×3) | Flask shaking |
| teams | Users | `icon-bounce` (translateY 0→-4px→0) | People jumping |
| logs | Terminal | `icon-blink` (opacity 1→0.3→1) | Cursor blinking |

## Implementation

1. Add class `tab-icon` to the `<component :is="tab.icon">` element in the template.
2. Define all CSS keyframes in `<style scoped>`.
3. Apply animations via CSS selectors:
   ```css
   .tab-item[data-tab-id="workflows"]:hover .tab-icon { animation: icon-spin 0.45s ease-out; }
   /* ... one rule per tab */
   ```
4. Set `animation-fill-mode: none` (default) so icon returns to its resting state after the animation ends.
5. `prefers-reduced-motion` media query wraps all animation rules — users with motion sensitivity see no animation.

## Constraints

- Text labels (`<span>`) are untouched.
- No JS involved; pure CSS.
- Active tab (primary background) still shows animation on hover — this is intentional (keeps interaction feedback consistent).
- Animation duration target: 350–500 ms per icon.
