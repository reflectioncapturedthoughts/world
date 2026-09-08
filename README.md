# 🌍 Videos of the World

A growing collection of short cinematic films celebrating the beauty of the
planet — mountains, oceans, forests, night skies and the wonders of the world.

## Watch

- Open **`videos/gallery.html`** in a browser for the full collection with
  posters and inline players.
- Or play any film directly — every file in `videos/` is a standalone
  MP4 (1920×1080, 25 fps, H.264, faststart).

## The films

| Film | Scenes | Length | Status |
|---|---|---|---|
| The Mountains | golden peaks · Himalayan dawn · alpine lake · storm spires · misty ridges · glacier aerial | ~23 s | ✅ |
| The Ocean | atoll lagoon · golden barrel · storm cliffs · deep-blue sailboat *(+2 scenes pending)* | ~19 s | ✅ v1 |
| The Forest | mossy falls · redwood light · bamboo path · autumn fog · emerald river · canopy dawn | ~23 s | ⏳ next |
| The Night Sky | aurora fjord · Milky Way arch · star trails · aurora cabin · alpine stars · meteor dunes | ~23 s | ⏳ queued |
| Wonders of the World | Machu Picchu · Taj Mahal · Great Wall · Pyramids of Giza · Santorini · Eiffel Tower | ~23 s | ⏳ queued |

Each film is built the same way: six stills → Ken Burns motion (slow zooms,
pans and tilts) → 0.8 s crossfades → cinematic title card with subtitle →
fade from/to black.

## How they're made

- **Imagery** — photorealistic landscape photography generated in the style
  of the free stock libraries that inspired this project (Unsplash, Pexels,
  Pixabay). The build sandbox's firewall blocks direct downloads from those
  CDNs, so equivalent imagery is generated locally instead.
- **Assembly** — `scripts/build_videos.py` (Python) driving ffmpeg
  (`zoompan` Ken Burns motion, `xfade` transitions, PIL-rendered title
  overlays, libx264 encode).

Rebuild everything (or one film):

```bash
pip install --user --break-system-packages pillow imageio-ffmpeg matplotlib
python3 scripts/build_videos.py                 # all films
python3 scripts/build_videos.py the-mountains   # a single film
```

## Layout

```
assets/themes/    source stills, one folder per film
build/titles/     rendered title-card overlays (RGBA PNG)
build/manifest.json  build metadata (durations, sizes)
scripts/          build tooling
videos/           final MP4s + posters/ + gallery.html
```
