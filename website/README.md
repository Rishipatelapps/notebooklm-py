# Beef Eating in the Vedas — Website

A single-page, self-contained website presenting the article
["Beef Eating in Vedas and Other Hindu Texts"](https://medium.com/@rishipatelapps/beef-eating-in-vedas-and-other-hindu-texts-716250747f6b)
by Rishi Patel.

## Usage

Everything lives in `index.html` — no build step, no dependencies (all CSS and
JS are inline; the only external request is an optional Devanagari web font
that falls back to system fonts offline). Open it directly in a browser:

```bash
open website/index.html        # macOS
xdg-open website/index.html    # Linux
```

Or serve it locally:

```bash
python -m http.server -d website 8000
```

It can be hosted as-is on GitHub Pages, Netlify, Vercel, or any static host.

## Features

- Manuscript-inspired design: parchment palette, maroon/gold accents, drop caps
- Native Devanagari typography: Sanskrit chapter marks, key-term banners with
  IAST transliteration and glosses, and Devanagari scholar names — crisp on
  every screen density, dark-mode friendly, and selectable (unlike screenshots)
- Sticky table of contents with active-section highlighting
- Reading progress bar and scroll-reveal animations
- 50+ primary-source quotations rendered as citation cards
- Claim-vs-rebuttal panels for the apologetic arguments addressed in the article
- Fully responsive, works on mobile
