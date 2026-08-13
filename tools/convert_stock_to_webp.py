"""img/stock/*.png → img/stock_web/*.webp（ファイル名stem維持）"""
from pathlib import Path
import sys

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "img" / "stock"
DST = ROOT / "img" / "stock_web"


def main() -> int:
    if not SRC.exists():
        print(f"source missing: {SRC}", file=sys.stderr)
        return 1

    DST.mkdir(parents=True, exist_ok=True)
    files = sorted([*SRC.glob("*.png"), *SRC.glob("*.jpg"), *SRC.glob("*.jpeg")])
    print(f"converting {len(files)} files -> {DST}")

    ok = fail = 0
    for i, path in enumerate(files, 1):
        out = DST / f"{path.stem}.webp"
        try:
            with Image.open(path) as im:
                if im.mode not in ("RGB", "RGBA"):
                    im = im.convert("RGBA" if "A" in im.getbands() else "RGB")
                im.save(out, "WEBP", quality=82, method=4)
            ok += 1
        except Exception as e:
            fail += 1
            print(f"FAIL {path.name}: {e}", file=sys.stderr)
        if i % 20 == 0 or i == len(files):
            print(f"  {i}/{len(files)} done")

    webps = list(DST.glob("*.webp"))
    total = sum(f.stat().st_size for f in webps)
    print(f"done: ok={ok} fail={fail} count={len(webps)} size_mb={total / 1024 / 1024:.1f}")
    return 0 if fail == 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())
