# Beef Eating in the Vedas — Website

A single-page, self-contained website presenting the article
["Beef Eating in Vedas and Other Hindu Texts"](https://medium.com/@rishipatelapps/beef-eating-in-vedas-and-other-hindu-texts-716250747f6b)
by Rishi Patel.

## Usage

Everything lives in `index.html` — no build step, no dependencies, no external
requests (all CSS and JS are inline). Open it directly in a browser:

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
- Sticky table of contents with active-section highlighting
- Reading progress bar and scroll-reveal animations
- 50+ primary-source quotations rendered as citation cards
- Claim-vs-rebuttal panels for the apologetic arguments addressed in the article
- Fully responsive, works on mobile
