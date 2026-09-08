#!/usr/bin/env python3
"""
Build the 'world' video collection.

Each video: 6 stills -> Ken Burns motion (ffmpeg zoompan) -> crossfades (xfade)
-> cinematic title overlay (PIL-rendered PNG) -> 1080p25 H.264 MP4 + poster.

Usage:
    python3 scripts/build_videos.py                # build every film whose
                                                   # images are ready
    python3 scripts/build_videos.py the-mountains  # build one film
"""
import html
import json
import os
import subprocess
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FPS = 25
FADE = 0.8                 # crossfade duration (s)
PRE_W, PRE_H = 2400, 1350  # pre-scale size fed to zoompan (motion headroom)
OUT_W, OUT_H = 1920, 1080
CRF = "21"


def find_ffmpeg():
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        pass
    p = os.path.expanduser(
        "~/.local/lib/python3.11/site-packages/imageio_ffmpeg/"
        "binaries/ffmpeg-linux-x86_64-v7.0.2")
    if os.path.exists(p):
        return p
    return "ffmpeg"


# ---------------------------------------------------------------- motions
def motion(kind, n):
    """Return (z, x, y) zoompan expressions for n output frames."""
    m = n - 1
    cx, cy = "(iw-iw/zoom)/2", "(ih-ih/zoom)/2"
    table = {
        "zoom_in":     (f"1+0.14*on/{m}", cx, cy),
        "zoom_out":    (f"1.14-0.14*on/{m}", cx, cy),
        "zoom_top":    (f"1+0.14*on/{m}", cx, "(ih-ih/zoom)*0.22"),
        "zoom_bottom": (f"1+0.14*on/{m}", cx, "(ih-ih/zoom)*0.78"),
        "pan_right":   ("1.20", f"(iw-iw/zoom)*on/{m}", cy),
        "pan_left":    ("1.20", f"(iw-iw/zoom)*(1-on/{m})", cy),
        "tilt_down":   ("1.16", cx, f"(ih-ih/zoom)*on/{m}"),
        "tilt_up":     ("1.16", cx, f"(ih-ih/zoom)*(1-on/{m})"),
    }
    return table[kind]


# ---------------------------------------------------------------- titles
def font_path(name):
    import matplotlib
    return os.path.join(os.path.dirname(matplotlib.__file__),
                        "mpl-data", "fonts", "ttf", name)


def tracked_width(draw, text, font, tracking):
    return sum(draw.textlength(c, font=font) for c in text) \
        + tracking * max(0, len(text) - 1)


def draw_tracked(draw, x, y, text, font, fill, tracking):
    for c in text:
        draw.text((x, y), c, font=font, fill=fill)
        x += draw.textlength(c, font=font) + tracking


def make_title_png(path, title, subtitle):
    from PIL import Image, ImageDraw, ImageFont
    W, H = OUT_W, OUT_H
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    # soft dark gradient across the lower third for legibility
    grad = Image.new("L", (1, H), 0)
    for y in range(H):
        t = max(0.0, (y / H - 0.60) / 0.40)
        grad.putpixel((0, y), int(170 * t * t))
    mask = grad.resize((W, H))
    black = Image.new("RGBA", (W, H), (5, 8, 12, 255))
    img.paste(black, (0, 0), mask)

    d = ImageDraw.Draw(img)
    f_title = ImageFont.truetype(font_path("DejaVuSans-Bold.ttf"), 62)
    f_sub = ImageFont.truetype(font_path("DejaVuSans.ttf"), 26)

    # thin gold accent line
    d.rectangle([(W - 150) / 2, 786, (W + 150) / 2, 788],
                fill=(212, 175, 55, 210))

    ty, sy = 816, 912
    tw = tracked_width(d, title, f_title, 22)
    draw_tracked(d, (W - tw) / 2, ty + 3, title, f_title, (0, 0, 0, 150), 22)
    draw_tracked(d, (W - tw) / 2, ty, title, f_title, (255, 255, 255, 248), 22)

    sw = tracked_width(d, subtitle, f_sub, 9)
    draw_tracked(d, (W - sw) / 2, sy + 2, subtitle, f_sub, (0, 0, 0, 140), 9)
    draw_tracked(d, (W - sw) / 2, sy, subtitle, f_sub, (222, 228, 236, 225), 9)
    img.save(path)


# ---------------------------------------------------------------- build
def qc_image(path):
    from PIL import Image, ImageStat
    im = Image.open(path)
    im.load()
    if im.width < 1024 or im.height < 576:
        raise SystemExit(f"QC FAIL {path}: too small {im.size}")
    stat = ImageStat.Stat(im.convert("L"))
    if stat.stddev[0] < 15:
        raise SystemExit(f"QC FAIL {path}: looks blank (stddev "
                         f"{stat.stddev[0]:.1f})")
    return im.size


def build_theme(theme, ffmpeg):
    slug = theme["slug"]
    shots = theme["shots"]
    for p, _m in shots:
        qc_image(os.path.join(ROOT, p))

    frames = theme.get("frames") or \
        [162] + [105] * (len(shots) - 1)  # first shot holds the title
    assert len(frames) == len(shots), "frames list must match shots"
    durs = [f / FPS for f in frames]
    total = sum(durs) - FADE * (len(shots) - 1)

    os.makedirs(os.path.join(ROOT, "build", "titles"), exist_ok=True)
    title_png = os.path.join(ROOT, "build", "titles", f"{slug}.png")
    make_title_png(title_png, theme["title"], theme["subtitle"])

    out = os.path.join(ROOT, "videos", f"{slug}.mp4")
    cmd = [ffmpeg, "-y", "-hide_banner", "-loglevel", "error"]
    for p, _m in shots:
        cmd += ["-i", os.path.join(ROOT, p)]
    cmd += ["-loop", "1", "-t", f"{total:.3f}", "-i", title_png]

    parts = []
    for i, (_p, m) in enumerate(shots):
        z, x, y = motion(m, frames[i])
        parts.append(
            f"[{i}:v]scale={PRE_W}:{PRE_H}:force_original_aspect_ratio=increase:"
            f"flags=lanczos,crop={PRE_W}:{PRE_H},"
            f"zoompan=z='{z}':x='{x}':y='{y}':d={frames[i]}:"
            f"s={OUT_W}x{OUT_H}:fps={FPS},"
            # NB: fps+settb are REQUIRED after zoompan for xfade (CFR inputs),
            # and setpts must NOT be used (it invalidates the frame rate).
            f"fps={FPS},settb=AVTB,setsar=1,unsharp=5:5:0.35:5:5:0[v{i}]")

    cur = "v0"
    offset = durs[0] - FADE
    for i in range(1, len(shots)):
        nxt = f"x{i}"
        parts.append(f"[{cur}][v{i}]xfade=transition=fade:"
                     f"duration={FADE}:offset={offset:.3f}[{nxt}]")
        cur = nxt
        if i < len(shots) - 1:
            offset += durs[i] - FADE

    n = len(shots)
    parts.append(f"[{n}:v]format=rgba,fade=t=in:st=1.0:d=0.9:alpha=1,"
                 f"fade=t=out:st=4.2:d=0.9:alpha=1[tl]")
    parts.append(f"[{cur}][tl]overlay=0:0,"
                 f"fade=t=in:st=0:d=0.7,"
                 f"fade=t=out:st={total - 1.1:.3f}:d=1.1,"
                 f"format=yuv420p[vout]")

    cmd += ["-filter_complex", ";".join(parts),
            "-map", "[vout]",
            "-c:v", "libx264", "-preset", "medium", "-crf", CRF,
            "-movflags", "+faststart", "-r", str(FPS),
            "-t", f"{total:.3f}", out]

    t0 = time.time()
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        print(r.stderr[-4000:])
        raise SystemExit(f"ffmpeg failed for {slug}")
    enc = time.time() - t0

    # poster frame with the title visible
    poster = os.path.join(ROOT, "videos", "posters", f"{slug}.jpg")
    subprocess.run([ffmpeg, "-y", "-hide_banner", "-loglevel", "error",
                    "-ss", "3.0", "-i", out, "-frames:v", "1", "-q:v", "3",
                    poster], check=True)

    size = os.path.getsize(out)
    print(f"[ok] {slug}: {total:.1f}s, {size/1e6:.1f} MB, "
          f"encoded in {enc:.0f}s")
    return {"slug": slug, "title": theme["title"],
            "subtitle": theme["subtitle"],
            "path": f"{slug}.mp4", "poster": f"posters/{slug}.jpg",
            "duration": total, "size": size}


# ---------------------------------------------------------------- gallery
GALLERY_TMPL = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Videos of the World</title>
<style>
  :root { color-scheme: dark; }
  body { margin:0; background:#0b0f14; color:#e8edf2;
         font-family:'Segoe UI', system-ui, -apple-system, sans-serif; }
  header { text-align:center; padding:56px 20px 8px; }
  header h1 { font-size:34px; letter-spacing:10px; font-weight:600;
              margin:0 0 10px; }
  header p { color:#9fb0c0; letter-spacing:2px; margin:0 0 40px;
             font-size:14px; }
  main { max-width:920px; margin:0 auto; padding:0 20px 80px; }
  .card { margin-bottom:56px; background:#121820;
          border:1px solid #1f2933; border-radius:12px; overflow:hidden; }
  video { display:block; width:100%; aspect-ratio:16/9; background:#000; }
  .meta { padding:18px 24px 20px; }
  .meta h2 { margin:0 0 6px; font-size:19px; letter-spacing:5px;
             font-weight:600; }
  .meta p { margin:0; color:#9fb0c0; font-size:13.5px; letter-spacing:1px; }
  footer { text-align:center; color:#5c6b7a; font-size:12px;
           letter-spacing:2px; padding:0 0 48px; }
</style>
</head>
<body>
<header>
  <h1>VIDEOS OF THE WORLD</h1>
  <p>FIVE SHORT FILMS &middot; 1080p &middot; 25 FPS</p>
</header>
<main>
{{CARDS}}
</main>
<footer>GENERATED IN THE WORLD REPOSITORY</footer>
</body>
</html>
"""


def write_gallery(manifest):
    ordered = [manifest[t["slug"]] for t in THEMES if t["slug"] in manifest]
    cards = []
    for r in ordered:
        mb = r["size"] / 1e6
        cards.append(f"""  <div class="card">
    <video controls preload="metadata" poster="{r['poster']}">
      <source src="{r['path']}" type="video/mp4">
    </video>
    <div class="meta">
      <h2>{html.escape(r['title'])}</h2>
      <p>{html.escape(r['subtitle'].title())} &middot; {r['duration']:.0f} seconds &middot; 1080p &middot; {mb:.1f} MB</p>
    </div>
  </div>""")
    page = GALLERY_TMPL.replace("{{CARDS}}", "\n".join(cards))
    with open(os.path.join(ROOT, "videos", "gallery.html"), "w") as f:
        f.write(page)


# ---------------------------------------------------------------- themes
THEMES = [
    {
        "slug": "the-mountains",
        "title": "THE MOUNTAINS",
        "subtitle": "WHERE THE EARTH TOUCHES THE SKY",
        "shots": [
            ("assets/themes/mountains/01-golden-peaks.jpg", "zoom_in"),
            ("assets/themes/mountains/02-himalaya-dawn.jpg", "zoom_top"),
            ("assets/themes/mountains/03-alpine-lake.jpg", "zoom_in"),
            ("assets/themes/mountains/04-storm-spires.jpg", "zoom_out"),
            ("assets/themes/mountains/05-ridged-mist.jpg", "pan_right"),
            ("assets/themes/mountains/06-glacier-aerial.jpg", "pan_left"),
        ],
    },
    {
        "slug": "the-ocean",
        "title": "THE OCEAN",
        "subtitle": "THE BLUE HEART OF THE PLANET",
        # v1: 4 scenes (palm beach + sea arch scenes arrive with the next
        # image batch, then this becomes a 6-scene film)
        "frames": [162, 126, 126, 126],
        "shots": [
            ("assets/themes/ocean/01-atoll-lagoon.jpg", "pan_right"),
            ("assets/themes/ocean/02-golden-barrel.jpg", "zoom_in"),
            ("assets/themes/ocean/03-storm-cliffs.jpg", "zoom_out"),
            ("assets/themes/ocean/04-sailboat-deep-blue.jpg", "pan_left"),
        ],
    },
    {
        "slug": "the-forest",
        "title": "THE FOREST",
        "subtitle": "RIVERS, MIST AND FALLING WATER",
        "shots": [
            ("assets/themes/forest/01-mossy-falls.jpg", "tilt_up"),
            ("assets/themes/forest/02-redwood-rays.jpg", "zoom_in"),
            ("assets/themes/forest/03-bamboo-path.jpg", "zoom_in"),
            ("assets/themes/forest/04-autumn-fog.jpg", "pan_right"),
            ("assets/themes/forest/05-emerald-river.jpg", "pan_left"),
            ("assets/themes/forest/06-canopy-dawn.jpg", "zoom_out"),
        ],
    },
    {
        "slug": "the-night-sky",
        "title": "THE NIGHT SKY",
        "subtitle": "AURORAS AND THE MILKY WAY",
        "shots": [
            ("assets/themes/night-sky/01-aurora-fjord.jpg", "zoom_in"),
            ("assets/themes/night-sky/02-milky-way-arch.jpg", "zoom_in"),
            ("assets/themes/night-sky/03-star-trails.jpg", "zoom_out"),
            ("assets/themes/night-sky/04-aurora-cabin.jpg", "zoom_in"),
            ("assets/themes/night-sky/05-alpine-stars.jpg", "zoom_in"),
            ("assets/themes/night-sky/06-meteor-dunes.jpg", "pan_right"),
        ],
    },
    {
        "slug": "wonders-of-the-world",
        "title": "WONDERS OF THE WORLD",
        "subtitle": "ICONS OF NATURE AND HUMANKIND",
        "shots": [
            ("assets/themes/wonders/01-machu-picchu.jpg", "zoom_out"),
            ("assets/themes/wonders/02-taj-mahal.jpg", "zoom_in"),
            ("assets/themes/wonders/03-great-wall.jpg", "pan_right"),
            ("assets/themes/wonders/04-pyramids.jpg", "pan_left"),
            ("assets/themes/wonders/05-santorini.jpg", "zoom_in"),
            ("assets/themes/wonders/06-eiffel-tower.jpg", "zoom_in"),
        ],
    },
]


def main():
    only = sys.argv[1] if len(sys.argv) > 1 else None
    ffmpeg = find_ffmpeg()
    print("ffmpeg:", ffmpeg)
    manifest_path = os.path.join(ROOT, "build", "manifest.json")
    manifest = {}
    if os.path.exists(manifest_path):
        with open(manifest_path) as f:
            manifest = json.load(f)
    for theme in THEMES:
        if only and theme["slug"] != only:
            continue
        missing = [p for p, _m in theme["shots"]
                   if not os.path.exists(os.path.join(ROOT, p))]
        if missing:
            print(f"[skip] {theme['slug']}: {len(missing)} image(s) missing "
                  f"(first: {missing[0]})")
            continue
        manifest[theme["slug"]] = build_theme(theme, ffmpeg)
    if manifest:
        os.makedirs(os.path.dirname(manifest_path), exist_ok=True)
        with open(manifest_path, "w") as f:
            json.dump(manifest, f, indent=2)
        write_gallery(manifest)
        print("\nsummary")
        for t in THEMES:
            if t["slug"] in manifest:
                r = manifest[t["slug"]]
                print(f"  videos/{r['path']:<28} {r['duration']:5.1f}s  "
                      f"{r['size']/1e6:6.1f} MB")


if __name__ == "__main__":
    main()
