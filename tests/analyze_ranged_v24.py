"""Check attack-key bow use with Nail Arts unlocked and transmitted impact direction."""
import argparse
import json
import math
import re
from pathlib import Path


def analyze(root):
    def read(name):
        return json.loads((root / name).read_text(encoding="utf-8-sig"))

    result = read("falseknight-bow-09.json")
    mc = read("falseknight-bow-minecraft-09.json")
    assert result.get("complete") and mc.get("complete")
    bow_rows = [s for s in result["samples"] if s["heldFlags"] == 2]
    assert bow_rows and not any(s["nailCharging"] for s in bow_rows)
    assert max(s["useTicks"] for s in mc["samples"]) >= 20
    assert mc["samples"][0]["ammo"] > mc["samples"][-1]["ammo"]
    assert any(s["arrows"] for s in mc["samples"])
    assert any(s["attackInput"] for s in bow_rows)
    pattern = r"HollowCraft: hit (.+?) for ([\d.]+) \(direction ([-\d.Ee]+), ([-\d.Ee]+);"
    events = re.findall(pattern, (root / "minecraft-05.log").read_text(encoding="utf-8-sig"))
    hits = [h for h in result["hits"] if h["attackType"] == "Generic"]
    assert len(events) == len(hits) and len(hits) >= 5
    errors = []
    for (name, damage, dx, dy), hit in zip(events, hits):
        assert hit["name"] == name and hit["DamageDealt"] == round(float(damage) * 3)
        expected = math.degrees(math.atan2(float(dy), float(dx))) % 360
        error = abs((hit["Direction"] - expected + 180) % 360 - 180)
        assert error < .001, (expected, hit["Direction"])
        errors.append(error)
    assert any(h["before"] > h["after"] for h in hits)
    art = read("nail-art-09.json")
    assert art.get("complete") and any(s["nailCharging"] for s in art["samples"])
    assert any(s["animation"] == "NA Big Slash" for s in art["samples"])
    refill = read("refill-status-08.json")
    assert refill["arrows"] == 64 and not refill["creative"]
    summary = dict(passed=True, nativeImpacts=len(hits), maximumDirectionErrorDegrees=max(errors),
                   maximumBowUseTicks=max(s["useTicks"] for s in mc["samples"]),
                   bowDoesNotChargeNailArt=True, swordNailArtPreserved=True, refillArrows=64, creative=False)
    (root / "ranged-v24-summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("evidence", type=Path)
    analyze(parser.parse_args().evidence)
