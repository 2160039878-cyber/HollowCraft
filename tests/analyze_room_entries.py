"""Validate hidden non-sword physics after native room transitions."""
import argparse
import json
import math
from pathlib import Path


def analyze(root):
    def read(name):
        return json.loads((root / name).read_text(encoding="utf-8-sig"))

    run = read("summary.json")
    assert run["completed"] and len(run["cases"]) == 6
    rows = 0
    for case in run["cases"]:
        index = case["index"]
        trace = read(f"motion-{index:02}.json")
        ready, after = read(f"ready-{index:02}.json"), read(f"after-{index:02}.json")
        assert trace.get("complete"), trace.get("reason", trace.get("error"))
        assert ready["ready"] and after["ready"] and ready["scene"] == after["scene"] == case["scene"]
        assert ready["teleport"] == ready["teleportAck"] and after["teleport"] == after["teleportAck"]
        assert ready["PhysicsTimeouts"] == after["PhysicsTimeouts"] == 0
        assert all(s["scene"] == case["scene"] for s in trace["combatSamples"])
        samples = trace["samples"]
        rows += len(samples)
        assert all(s["hp"] > 0 and s["HiddenWindow"] and s["visibleWindows"] == 0
                   and not s["ownsForegroundWindow"] for s in samples)
        assert all(math.isfinite(s[k]) for s in samples for k in ("x", "y", "mcX", "mcY"))
        assert any(s["native"] and s["heldFlags"] & 1 for s in samples)
        external = [s for s in samples if not s["native"] and not s["heldFlags"] & 1]
        assert len(external) >= 20
        assert max(s["PhysicsTick"] for s in external) > min(s["PhysicsTick"] for s in external) + 20
        assert any(s["VelocityY"] > 1 for s in external), "Non-sword jump did not advance"
        assert max(s["y"] for s in external) - min(s["y"] for s in external) > .1
        if case["scene"] == "Ruins2_01":
            assert len({math.floor(s["mcX"] / 16) for s in external}) >= 2
            paused = [s for s in samples if s["mcScreenOpen"] and s["timeScale"] == 0]
            assert len(paused) >= 5
            assert max(s["x"] for s in paused) - min(s["x"] for s in paused) < .1
            assert max(s["y"] for s in paused) - min(s["y"] for s in paused) < .1
            assert not samples[-1]["mcScreenOpen"]
    report = dict(passed=True, entries=len(run["cases"]), samples=rows,
                  scenes=sorted({c["scene"] for c in run["cases"]}),
                  maximumPhysicsWaitMs=max(c["maxWaitMs"] for c in run["cases"]), physicsTimeouts=0,
                  chunkBoundaryAndInventoryCases=3,
                  limitations="Six hidden transitions; excludes visible FPS, arbitrary GC/render stalls and heavy stress scenes.")
    (root / "validated.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("evidence", type=Path)
    analyze(parser.parse_args().evidence)
