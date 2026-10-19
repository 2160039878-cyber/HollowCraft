"""Check recorded native TNT plane/persistence and bow shield/flying regressions."""
import argparse
import json
from pathlib import Path


def analyze(root):
    def read(name):
        return json.loads((root / name).read_text(encoding="utf-8-sig"))

    chain = read("redstone-chain-01.json")
    assert chain[0]["tntCount"] == 20
    assert next(e for e in chain if e["event"] == "lever-on")["tick"] == 40
    assert next(e for e in chain if e["event"] == "repeater-on")["tick"] == 44
    blasts = [e for e in chain if e["event"] == "exploded"]
    assert len(blasts) == 20 and all(e["power"] == 4 and e["z"] == .5 for e in blasts)
    assert len({(e["tick"], e["x"], e["y"]) for e in blasts}) == 20
    assert any(e["dugCellsAtPlane"] for e in blasts)
    assert chain[-1]["event"] == "finished" and chain[-1]["remaining"] == 0
    assert not chain[-1]["tntBlockRemaining"]

    before = read("tnt-before-leave.json")["tnt"][0]
    away = read("tnt-away-a.json")["tnt"][0]
    returned = read("tnt-returned.json")["tnt"][0]
    assert 0 < away["fuse"] <= before["fuse"]
    assert read("tnt-away-b.json")["tnt"] == []
    assert away["id"] != returned["id"]  # A different native entity was loaded from the saved chunk.
    assert all(away[k] == returned[k] for k in ("fuse", "x", "y", "z", "tags"))
    assert returned["z"] == .5 and returned["tags"] == before["tags"]
    assert read("room-fixture-abort.json")[-1]["reason"] == "scope changed"
    resumed = read("room-fuse-resumed.json")
    assert resumed["complete"]
    blast = read("runtime-final.json")["playerExplosion"]
    assert blast["raw"] == 2 and blast["masks"] == 1 and blast["before"] - blast["after"] == 1
    assert not blast["immune"] and 0 < blast["exposure"] < 1
    assert any(h["source"] is None and h["before"] == blast["before"] and h["after"] == blast["after"]
               for h in resumed["received"])

    bow = read("shield-bow-02.json")
    assert bow["complete"]
    shield = [h for h in bow["hits"] if h["name"] == "Great Shield Zombie"]
    blocked = [h for h in shield if h["invincible"]]
    exposed = [h for h in shield if not h["invincible"]]
    assert blocked and all(h["before"] == h["after"] for h in blocked)
    assert exposed and all(h["before"] - h["after"] == h["DamageDealt"] > 0 for h in exposed)
    flying = [h for h in bow["hits"] if h["name"].startswith("Ruins Flying Sentry") and h["before"] > h["after"]]
    assert flying and all(h["before"] - h["after"] == h["DamageDealt"] for h in flying)
    assert all(h["attackType"] == "Generic" and not h["IgnoreInvulnerable"] for h in shield + flying)
    for name in ("chain-01.json", "room-fuse-resumed.json", "shield-bow-02.json"):
        samples = read(name)["samples"]
        assert samples and all(s["HiddenWindow"] and s["visibleWindows"] == 0
                               and not s["ownsForegroundWindow"] for s in samples)

    summary = dict(passed=True, tntExplosions=len(blasts), planeZ=.5,
                   savedFuse=returned["fuse"], resumedPlayerDamage=1,
                   shieldBlocks=len(blocked), shieldDamage=sum(h["DamageDealt"] for h in exposed),
                   flyingDamage=sum(h["DamageDealt"] for h in flying), backgroundOnly=True,
                   limitations="Chunk reload, not full process restart. Shield front blocks/exposed window only; flying hit, not kill. No visual or performance acceptance.")
    (root / "combat-plane-summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("evidence", type=Path)
    analyze(parser.parse_args().evidence)
