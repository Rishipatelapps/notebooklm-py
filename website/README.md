# Beef Eating in the Vedas — Website

A single-page, self-contained website presenting the article
["Beef Eating in Vedas and Other Hindu Texts"](https://medium.com/@rishipatelapps/beef-eating-in-vedas-and-other-hindu-texts-716250747f6b)
by Rishi Patel.

## Usage

Everything lives in `index.html` — no build step, no dependencies, no
external requests. Open it directly in a browser:

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

- Dark editorial design: near-black background, warm gold accent, serif body
  text paired with a sans display face for headings
- Stat strip summarizing the scope of the sourcing (citation count, Vedas
  examined, etc.)
- Sticky-free table of contents linking to every section
- Block-quoted primary-source citations with attribution
- Sanskrit (Devanagari) section labels alongside the English headings
- Fully responsive single-column layout, readable on any screen width
