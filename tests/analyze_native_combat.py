"""Check recorded native arena damage, responder selection, and hidden execution."""
import argparse
import json
import re
from pathlib import Path


def analyze(root):
    def read(name):
        return json.loads((root / name).read_text(encoding="utf-8-sig"))

    names = ["hornet-combat-01.json", "hornet-combat-02.json", "falseknight-bow-01.json",
             "falseknight-sword-fixed.json", "mantis-bow-fixed-02.json", "mantis-tnt-01.json"]
    cases = {name: read(name) for name in names}
    rows = [s for case in cases.values() for s in case["samples"]]
    assert all(c.get("complete") for c in cases.values())
    assert rows and all(s["HiddenWindow"] and s["visibleWindows"] == 0
                        and not s["ownsForegroundWindow"] for s in rows)

    # The failed run is retained to distinguish the cache regression from a missed attack.
    old = cases["hornet-combat-02.json"]["hits"]
    assert any(h["before"] - h["after"] == 5 for h in old)
    sword = cases["falseknight-sword-fixed.json"]["hits"]
    assert len(sword) == 3
    assert all(h["attackType"] == "Nail" and h["DamageDealt"] == 21
               and h["before"] - h["after"] == 21 for h in sword)
    assert read("nail-fsm-before.json")["nailDamage"] == 21

    bow = cases["falseknight-bow-01.json"]["hits"]
    assert len(bow) == 1 and bow[0]["attackType"] == "Generic"
    assert bow[0]["DamageDealt"] == bow[0]["before"] - bow[0]["after"] == 15
    raw_hit = re.search(r"hit False Knight New for ([0-9.]+) ", (root / "bow-proxy-hit-log.txt").read_text())
    assert raw_hit and float(raw_hit.group(1)) * 3 == bow[0]["DamageDealt"]
    mc = read("falseknight-bow-minecraft-01.json")
    assert mc.get("cancelled") and mc.get("reason") == "scope changed"
    assert max(s["useTicks"] for s in mc["samples"]) >= 20
    arrows = {a["id"] for s in mc["samples"] for a in s["arrows"]}
    assert arrows

    hornet = cases["hornet-combat-01.json"]["received"]
    assert {d["source"] for d in hornet if d["before"] > d["after"]} == {"Needle", "Sphere Ball"}
    assert all(d["before"] - d["after"] in (0, 1) for d in hornet)
    assert any(d["before"] == d["after"] and d["invulnerable"] for d in hornet)

    duplicate_samples = 0
    for row in cases["mantis-bow-fixed-02.json"]["combatSamples"]:
        targets = row["targets"]
        if len(targets) != 2:
            continue
        assert len({t["objectId"] for t in targets}) == 1
        assert len({t["id"] for t in targets}) == 2
        assert sum(t["nativeResponder"] for t in targets) == 1
        duplicate_samples += 1
    assert duplicate_samples > 0
    counts = re.findall(r"HollowCraft: (\d+) REPO actors mirrored", (root / "mantis-proxy-log.txt").read_text())
    assert counts == ["1"], counts

    redstone = {e["event"]: e for e in read("mantis-redstone-01.json")}
    assert redstone["lever-on"]["tick"] == 40 and redstone["repeater-on"]["tick"] == 44
    assert redstone["exploded"]["power"] == 4 and not redstone["finished"]["tntBlockRemaining"]
    restored = read("restore.json")
    assert restored["originalProfileHashesMatch"] and restored["profileFiles"] == 18
    status = read("final-idle.json")
    summary = dict(scopedChecksPassed=True, hiddenSamples=len(rows), swordDamage=21, swordHits=len(sword),
                   bowDamage=15, bowMinecraftSamples=len(mc["samples"]), arrowsObserved=len(arrows),
                   duplicateHealthManagerSamples=duplicate_samples, nativeRespondersPerObject=1,
                   minecraftProxies=1, realHornetDamage=True, redstoneExplosionTick=redstone["exploded"]["tick"],
                   physicsTimeouts=status["PhysicsTimeouts"], maxPhysicsWaitMs=status["MaxPhysicsWaitMilliseconds"],
                   limitations=["No full Boss fight, phase, shield, flying-enemy or pogo acceptance.",
                                "Bow trace predates the responder/cache fix; fixed-build sword and proxy selection are checked separately.",
                                "No Boss was hit by the recorded redstone blast; Boss blast deduplication remains unverified.",
                                "One loading/mode-transfer timeout recovered; hidden traces do not establish 1080p performance."])
    (root / "native-combat-summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("evidence", type=Path)
    analyze(parser.parse_args().evidence)
