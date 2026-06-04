#!/usr/bin/env python3
"""Split public/parcels.json into chunks each <22MB so Cloudflare Pages can host them."""

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PUB = ROOT / "public"
SRC = PUB / "parcels.json"
N_CHUNKS = 10

def main():
    data = json.loads(SRC.read_text())
    feats = data["features"]
    print(f"loaded {len(feats)} features ({SRC.stat().st_size//1024} KB)")

    per = (len(feats) + N_CHUNKS - 1) // N_CHUNKS
    manifest = []
    for i in range(N_CHUNKS):
        chunk = feats[i*per:(i+1)*per]
        out = PUB / f"parcels-{i+1}.json"
        out.write_text(json.dumps({"type":"FeatureCollection","features":chunk}, ensure_ascii=False))
        size_kb = out.stat().st_size // 1024
        manifest.append({"file": f"parcels-{i+1}.json", "count": len(chunk), "size_kb": size_kb})
        print(f"  parcels-{i+1}.json: {len(chunk)} features, {size_kb} KB")

    # Also write a small manifest pointing to chunks
    (PUB / "parcels-manifest.json").write_text(json.dumps({
        "chunks": [m["file"] for m in manifest],
        "total": len(feats),
        "stats": manifest,
    }, ensure_ascii=False))
    print(f"\n✅ wrote parcels-manifest.json")


if __name__ == "__main__":
    main()
