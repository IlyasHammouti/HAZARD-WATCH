"""Inline the brand PNGs into the identity page, so the artifact is self-contained."""

import base64
import io
from pathlib import Path

HERE = Path(__file__).parent

IMAGES = {
    "__IMG_HORIZ_INK__":      "logo-horizontal-ink.png",
    "__IMG_HORIZ_PAPER__":    "logo-horizontal-paper.png",
    "__IMG_AVATAR_INK__":     "logo-avatar-ink.png",
    "__IMG_AVATAR_PAPER__":   "logo-avatar-paper.png",
    "__IMG_MONO_INK__":       "logo-monogram-ink.png",
    "__IMG_MONO_PAPER__":     "logo-monogram-paper.png",
    "__IMG_COVER_INK__":      "linkedin-page-cover-ink-1128x191.png",
    "__IMG_COVER_PAPER__":    "linkedin-page-cover-paper-1128x191.png",
    "__IMG_BANNER_INK__":     "linkedin-profile-banner-ink-1584x396.png",
    "__IMG_BANNER_PAPER__":   "linkedin-profile-banner-paper-1584x396.png",
}


def main():
    html = io.open(HERE / "identity_template.html", encoding="utf-8").read()
    for token, name in IMAGES.items():
        raw = (HERE / name).read_bytes()
        html = html.replace(token, "data:image/png;base64," + base64.b64encode(raw).decode())
    assert "__IMG_" not in html, "an image token was left unreplaced"
    out = HERE / "identity.html"
    io.open(out, "w", encoding="utf-8").write(html)
    print("%s  %.0f KB" % (out.name, out.stat().st_size / 1024))


if __name__ == "__main__":
    main()
