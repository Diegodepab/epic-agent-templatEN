---
trigger: glob
globs: "**/*.ts, **/*.tsx, **/*.js, **/*.jsx, **/*.astro, **/*.vue, **/*.svelte, **/*.html, **/*.css"
---

# Frontend Engineering, Performance & Accessibility Standards

> Visual direction (Minimalist Editorial, Fluid Interactive Canvas, or Creative Experimental) is governed by the single archetype selected in `_reference/SPEC.md` and its corresponding design skill. This rule enforces strictly technical frontend engineering.

## 1. Runtime Performance & Core Web Vitals (60fps Target)

- **Zero Main-Thread Blocking**: Avoid long tasks (>50ms) during initial load and interaction. Never ship runtime CSS JIT compilers (such as browser Tailwind CDN scripts) in production builds; always precompile and minify styles.
- **Zero Layout Shift (CLS < 0.05)**: Every `<img>`, `<video>`, `<svg>`, and `<canvas>` must declare explicit `width` and `height` attributes or a CSS `aspect-ratio`. Reserve `min-height` containers or skeletons for asynchronous content.
- **Asset Prioritization & Motion Hygiene**: Mark the primary above-the-fold visual with `loading="eager"` and `fetchpriority="high"`; lazy-load below-the-fold media. Animate compositor-friendly properties (`transform`, `opacity`) and always honor `@media (prefers-reduced-motion: reduce)`.

## 2. Accessibility (WCAG AA) & Responsive Ergonomics

- **Semantic DOM**: Use proper landmarks (`<header>`, `<main>`, `<nav>`, `<section>`), a single `<h1>` per view with sequential heading levels (`<h1>` -> `<h2>` -> `<h3>`), and `<button type="button">` for interactive triggers (never `<a href="#">`).
- **Accessible Naming (WCAG 2.5.3)**: Every interactive control must have an unambiguous accessible name. When `aria-label` is used on an element with visible text, it must include the visible text string.
- **Legibility & Touch Targets**: Maintain >= 4.5:1 text contrast, minimum `12px` (`0.75rem`) font size for readable metadata, touch targets >= `44x44px` (`48x48px` on mobile), and zero unintended horizontal page scroll down to `375px` viewport width.

## 3. Component Architecture & Anti-Slop Hygiene

- **Modular Separation**: Decouple presentational UI components from network calls, state stores, and business logic. Enforce strict TypeScript types (`strict: true`, no `any`).
- **Zero AI Slop**: Never inject fake statistics, generic filler copy ("empowering seamless solutions"), or decorative inline emojis (`🚀`, `✨`, `🔥`) in UI chrome, headings, buttons, or notifications.

## 4. Live Browser Verification

- After modifying UI components, styles, or client interactions, verify visual layout (Desktop and Mobile `375px` viewports), interactive states, and zero console/network errors using Antigravity's `browser` subagent.
