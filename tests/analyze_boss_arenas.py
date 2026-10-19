"""Validate native False Knight/Hornet victory traces; does not approve other combat gates."""
import argparse
import json
from pathlib import Path


def analyze(root):
    def read(name):
        return json.loads((root / name).read_text(encoding="utf-8-sig"))

    results = {}
    for name, scene in [("falseknight", "GG_False_Knight"), ("hornet", "GG_Hornet_1")]:
        case = read(name + "-fight-04.json")
        plan = read(name + "-fight-input-04.json")
        assert not any(s.get("Damage", 0) for s in plan) and not case["damage"]
        assert case.get("cancelled") and case["reason"] == "scene or peer changed"
        rows = case["samples"]
        assert case["combatSamples"][0]["scene"] == scene and rows[0]["hp"] == 11
        assert all(s["HiddenWindow"] and s["visibleWindows"] == 0 and not s["ownsForegroundWindow"] for s in rows)
        assert not any(d["before"] > 0 and d["after"] == 0 for d in case["received"])
        assert any(d["before"] > d["after"] for d in case["received"])
        hits = case["hits"]
        assert hits and all(h["attackType"] == "Nail" and h["DamageDealt"] == 32 for h in hits)
        assert case["bounces"] and any(h["source"] == "DownSlash" for h in hits)
        assert any(b["velocityY"] > 0 for b in case["bounces"])
        returned = read(name + "-victory-return.json")
        assert returned["scene"] == "GG_Workshop" and returned["ready"] and returned["gameState"] == "PLAYING"
        if name == "falseknight":
            resets = [h for h in hits if h["name"] == "Head" and h["before"] == 8 and h["after"] == 40]
            assert len(resets) == 3, "All three exposed-head phases must be completed"
        else:
            assert any(h["name"] == "Hornet Boss 1" and h["before"] > 0 and h["after"] <= 0 for h in hits)
        results[name] = dict(seconds=rows[-1]["t"], hitCalls=len(hits), bounceCalls=len(case["bounces"]),
                             damagePerNail=32, defeated=True, returned=True)
    assert (root / "host-04.log").read_text(encoding="utf-8-sig").count("Boss scene ended") == 2
    summary = dict(passed=True, bosses=results,
                   scope="Native attuned Godhome arenas; native Godseeker loadout with Heart and Strength, keyboard-action input only.",
                   limitations="Earlier v24 host build; excludes Mantis victory, other weapons, visuals and performance.")
    (root / "boss-arenas-summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("evidence", type=Path)
    analyze(parser.parse_args().evidence)
