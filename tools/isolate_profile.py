"""Give the task-owned game copy its own Unity data/PlayerPrefs namespace."""
from pathlib import Path
import hashlib
import shutil
import UnityPy

root = Path(r"E:\HollowCraft\game").resolve()
if not (root / ".hollowcraft-managed").is_file():
    raise SystemExit("Refusing to modify a game without the task-owned marker")
asset = root / "hollow_knight_Data" / "globalgamemanagers"
backup = root / "original-files" / "globalgamemanagers"
source_bytes = asset.read_bytes()
env = UnityPy.load(source_bytes)
settings = [obj for obj in env.objects if obj.type.name == "PlayerSettings"]
if len(settings) != 1:
    raise SystemExit("Expected one PlayerSettings object")
obj = settings[0]
tree = obj.read_typetree(check_read=False)
if tree.get("companyName") == "HollowCraft" and tree.get("productName") == "HollowCraftHK":
    print("Profile already isolated")
    raise SystemExit(0)
if tree.get("companyName") != "Team Cherry" or tree.get("productName") != "Hollow Knight":
    raise SystemExit("Unexpected game identity; preserving the file")
raw = obj.get_raw_data()
original_raw = raw
# ponytail: equal-length replacements preserve Unity 6 fields that UnityPy 1.25.4 does not decode.
# Replace this with full typetree serialization once its schema consumes the complete object.
for old, new in [(b"Team Cherry", b"HollowCraft"), (b"Hollow Knight", b"HollowCraftHK")]:
    if len(old) != len(new) or raw.count(old) != 1:
        raise SystemExit("Ambiguous serialized identity")
    raw = raw.replace(old, new, 1)
backup.parent.mkdir(parents=True, exist_ok=True)
if backup.exists():
    if backup.read_bytes() != source_bytes:
        raise SystemExit("The existing backup differs from this source; preserving both")
else:
    shutil.copy2(asset, backup)
obj.set_raw_data(raw)
temp = asset.with_suffix(".hollowcraft-new")
temp.write_bytes(env.file.save())
verify = UnityPy.load(temp.read_bytes())
verified = next(x for x in verify.objects if x.type.name == "PlayerSettings").read_typetree(check_read=False)
assert verified["companyName"] == "HollowCraft" and verified["productName"] == "HollowCraftHK"
assert len(raw) == len(original_raw)
temp.replace(asset)
print("Isolated profile: HollowCraft/HollowCraftHK")
print("Original file SHA256:", hashlib.sha256(backup.read_bytes()).hexdigest())
