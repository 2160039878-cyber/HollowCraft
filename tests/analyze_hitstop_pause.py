"""Regression check: native hit-stop must not override a bridge-owned pause."""
import argparse
import json
from pathlib import Path


def analyze(root):
    def read(name):
        return json.loads((root / name).read_text(encoding="utf-8-sig"))

    before = read("pause-leak-state-before.json")
    assert before["pausedByBridge"] and before["timeScale"] > 0
    a, b = read("hitstop-background-idle-a.json"), read("hitstop-background-idle-b.json")
    assert all(s["pausedByBridge"] and s["timeScale"] == 0 for s in (a, b))
    assert all(abs(a[k] - b[k]) < 1e-5 for k in ("heroX", "heroY", "mcX", "mcY"))
    assert a["PhysicsTimeouts"] == b["PhysicsTimeouts"] == 0
    stop = read("hitstop-background-stop.json")
    assert stop.get("complete") and [(d["before"], d["after"]) for d in stop["damage"]] == [(5, 4)]
    result = read("hitstop-inventory-resume.json")
    assert result.get("complete")
    assert [(d["before"], d["after"]) for d in result["damage"]] == [(4, 3)]
    rows = result["samples"]
    paused = [s for s in rows if s["mcScreenOpen"]]
    stable = [s for s in paused if s["t"] > paused[0]["t"] + .3]
    assert stable and all(s["timeScale"] == 0 for s in stable)
    for key in ("physicsX", "physicsY", "mcX", "mcY", "unityTime", "fixedTime"):
        assert max(s[key] for s in stable) - min(s[key] for s in stable) < .001, key
    assert rows[-1]["timeScale"] == 1 and rows[-1]["hp"] == 3 and not rows[-1]["mcScreenOpen"]
    assert all(s["HiddenWindow"] and s["visibleWindows"] == 0 and not s["ownsForegroundWindow"] for s in rows)
    summary = dict(passed=True, inventoryPausedSamples=len(stable), backgroundPositionStable=True,
                   nativeScaleResumed=1, playerHealth=3, physicsTimeouts=0)
    (root / "hitstop-pause-summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("evidence", type=Path)
    analyze(parser.parse_args().evidence)
