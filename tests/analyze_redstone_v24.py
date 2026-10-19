"""Verify native TNT chain events and the separately recorded Boss blast impact."""
import argparse
import json
from pathlib import Path


def analyze(root):
    def read(name):
        return json.loads((root / name).read_text(encoding="utf-8-sig"))

    chain = read("falseknight-redstone-chain-09.json")
    assert chain[0]["event"] == "built" and chain[0]["tntCount"] == 20
    assert next(e for e in chain if e["event"] == "lever-on")["tick"] == 40
    assert next(e for e in chain if e["event"] == "repeater-on")["tick"] == 44
    blasts = [e for e in chain if e["event"] == "exploded"]
    assert len(blasts) == 20 and all(e["power"] == 4 for e in blasts)
    assert len({(e["tick"], e["x"], e["y"], e["z"]) for e in blasts}) == 20
    assert any(e["dugCellsAtPlane"] for e in blasts)
    single = read("falseknight-redstone-09b.json")
    assert single[0]["tntCount"] == 1 and len([e for e in single if e["event"] == "exploded"]) == 1
    case = read("falseknight-tnt-09b.json")
    hits = [h for h in case["hits"] if h["source"] == "HollowCraft TNT blast"]
    assert len(hits) == 1 and hits[0]["name"] == "False Knight New"
    assert hits[0]["before"] == 260 and hits[0]["after"] == 257 and hits[0]["DamageDealt"] == 3
    assert hits[0]["sourceId"] != 0 and not hits[0]["IgnoreInvulnerable"]
    summary = dict(passed=True, nativeChainExplosions=20, firstExplosionTick=blasts[0]["tick"],
                   lastExplosionTick=blasts[-1]["tick"], nativeTerrainCellsChanged=True, bossBlastDamage=3,
                   limitations="Chain run ended on scene change; excludes 256-component/1080p performance, whole-Boss completion and broad multi-part blast coverage.")
    (root / "redstone-v24-summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("evidence", type=Path)
    analyze(parser.parse_args().evidence)
