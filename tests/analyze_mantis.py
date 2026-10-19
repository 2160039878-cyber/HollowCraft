"""Check native two-phase Mantis victory evidence from the hidden input probe."""
import argparse
import json
from pathlib import Path


def analyze(root):
    def read(name):
        return json.loads((root / name).read_text(encoding="utf-8-sig"))

    trace = read("mantis-fight.json")
    plan = read("mantis-fight-input.json")
    assert not any(step.get("Damage") or step.get("PlaceX") or step.get("Refill") for step in plan)
    assert not trace["damage"]
    assert trace.get("cancelled") and trace["reason"] == "scene or peer changed"
    samples = trace["samples"]
    assert samples and samples[0]["hp"] == 11
    assert all(s["HiddenWindow"] and s["visibleWindows"] == 0 and not s["ownsForegroundWindow"] for s in samples)
    assert all(s["hp"] > 0 for s in samples), "A death/respawn cannot count as victory"
    assert all(s["scene"] == "GG_Mantis_Lords" for s in trace["combatSamples"])
    real_hits = [h for h in trace["hits"] if h["before"] > h["after"]]
    bosses = {}
    for name, initial_hp in [("Mantis Lord", 400), ("Mantis Lord S1", 350), ("Mantis Lord S2", 350)]:
        hits = [h for h in real_hits if h["name"] == name]
        assert hits and hits[0]["before"] == initial_hp
        assert any(h["before"] > 0 and h["after"] <= 0 for h in hits), name + " not defeated"
        assert all(not h["IgnoreInvulnerable"] and (
            h["DamageDealt"] == 32 and h["attackType"] == "Nail"
            or h["DamageDealt"] == 30 and h["attackType"] == "Spell" and h["source"] == "Fireball2 Spiral(Clone)"
        ) for h in hits)
        bosses[name] = {"initialHp": initial_hp, "minimumHp": min(h["after"] for h in hits), "hits": len(hits)}
    received = [d for d in trace["received"] if d["before"] > d["after"]]
    assert received and all(d["after"] > 0 for d in received)
    assert any(h["source"] == "DownSlash" for h in real_hits)
    assert any(b["velocityY"] > 0 for b in trace["bounces"])
    returned = read("mantis-victory-return.json")
    assert returned["ready"] and returned["scene"] == "GG_Workshop" and returned["gameState"] == "PLAYING"
    assert "Boss scene ended" in (root / "host-victory.log").read_text(encoding="utf-8-sig")
    last_defeat = max(h["t"] for h in real_hits if h["after"] <= 0)
    heals = sum(s["hp"] > before["hp"] and s["t"] < last_defeat for before, s in zip(samples, samples[1:]))
    assert heals > 0, "Native focus must finish before the victory health reset"
    summary = dict(passed=True, seconds=samples[-1]["t"], bosses=bosses, damageEvents=len(received),
                   lowestPlayerHp=min(s["hp"] for s in samples), bounces=len(trace["bounces"]),
                   healingEvents=heals, nativeSpellHits=sum(h["attackType"] == "Spell" for h in real_hits),
                   scope="Native attuned Godhome fight; Heart, Strength and Quick Focus; nail/focus-cast action bindings only.",
                   limitations="No story entry, visible animation, audio or 1080p performance acceptance.")
    (root / "mantis-summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("evidence", type=Path)
    analyze(parser.parse_args().evidence)
