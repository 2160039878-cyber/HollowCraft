using System;
using HollowCraft;

static void Check(bool condition, string message)
{
    if (!condition) throw new InvalidOperationException(message);
}

if (args.Length == 2 && args[0] == "--explosion-vectors")
{
    using var data = System.Text.Json.JsonDocument.Parse(System.IO.File.ReadAllText(args[1]));
    int count = 0;
    foreach (var item in data.RootElement.GetProperty("cases").EnumerateArray())
    {
        float power=item.GetProperty("power").GetSingle(), distance=item.GetProperty("distance").GetSingle(),
            exposure=item.GetProperty("exposure").GetSingle(), expected=item.GetProperty("nativeDamage").GetSingle();
        Check(Math.Abs(DamageRules.Explosion(power,distance,exposure)-expected)<.00001f,"Damage must match the running Minecraft calculator");
        count++;
    }
    Check(count>=50,"Native comparison matrix is incomplete");
    Check(DamageRules.Player(DamageRules.Explosion(4,6,.5f))==2,"Fractional damage must be retained until mask conversion");
    Check(DamageRules.Explosion(4,9,1)==0 && DamageRules.Explosion(4,float.NaN,1)==0,"Invalid and out-of-range blasts must not damage");
    Check(DamageRules.ExplosionKnockback(4,4,.5f)==.25f && DamageRules.ExplosionKnockback(4,1,0)==0,"Knockback must attenuate with distance and exposure");
    Console.WriteLine($"PASS: {count} native explosion vectors, mask rounding, range and knockback");
    return;
}

if (args.Length == 2 && args[0] == "--checkpoint-io")
{
    string directory = System.IO.Path.GetFullPath(args[1]);
    Check(!System.IO.Directory.Exists(directory), "Use a new test directory");
    System.IO.Directory.CreateDirectory(directory);
    string path = System.IO.Path.Combine(directory, "control.json");
    CheckpointFiles.Write(path, System.Text.Encoding.UTF8.GetBytes("first"));
    using (var held = new System.IO.FileStream(path, System.IO.FileMode.Open, System.IO.FileAccess.Read, System.IO.FileShare.None))
    {
        Check(CheckpointFiles.ReadControl(path, true) == null, "A busy poll must defer without blocking");
        bool rejected = false;
        try { CheckpointFiles.ReadControl(path); } catch (System.IO.IOException) { rejected = true; }
        Check(rejected, "A busy commit pointer must never be treated as a missing checkpoint");
    }
    using (var held = new System.IO.FileStream(path, System.IO.FileMode.Open, System.IO.FileAccess.Read,
        System.IO.FileShare.ReadWrite | System.IO.FileShare.Delete))
        CheckpointFiles.Write(path, System.Text.Encoding.UTF8.GetBytes("second"));
    Check(CheckpointFiles.ReadControl(path) == "second", "Shared reads must allow atomic replacement");
    System.IO.File.WriteAllBytes(path, new byte[65537]);
    bool oversized = false;
    try { CheckpointFiles.ReadControl(path, true); } catch (System.IO.InvalidDataException) { oversized = true; }
    Check(oversized, "Size limits must remain enforced");
    Console.WriteLine("PASS: busy control reads, strict commit pointer, atomic replacement and size limit");
    return;
}

if(args.Length==1 && args[0]=="--terrain-edge")
{
    var boxes=new System.Collections.Generic.List<HollowCraft.World.Clip.Box> {
        new() {LoX=1,HiX=2,LoY=-1,HiY=1}};
    var parts=new System.Collections.Generic.List<(float From,float To)>();
    HollowCraft.World.Clip.SubtractSegment(0,0,3,0,boxes,parts);
    Check(parts.Count==2 && Math.Abs(parts[0].To-1f/3)<1e-6 && Math.Abs(parts[1].From-2f/3)<1e-6,"Only the intersecting edge interval must be removed");
    HollowCraft.World.Clip.SubtractSegment(3,0,0,0,boxes,parts);
    Check(parts.Count==2 && Math.Abs(parts[0].To-1f/3)<1e-6,"Reversed edges must retain their order");
    HollowCraft.World.Clip.SubtractSegment(1.5f,-2,1.5f,2,boxes,parts);
    Check(parts.Count==2 && parts[0].To==.25f && parts[1].From==.75f,"Vertical edges must be cut without division by zero");
    HollowCraft.World.Clip.SubtractSegment(0,2,3,2,boxes,parts);
    Check(parts.Count==1 && parts[0]==(0f,1f),"A disjoint edge must remain unchanged");
    boxes.Add(new() {LoX=0,HiX=1.5f,LoY=-1,HiY=1});
    HollowCraft.World.Clip.SubtractSegment(0,0,3,0,boxes,parts);
    Check(parts.Count==1 && Math.Abs(parts[0].From-2f/3)<1e-6,"Overlapping cuts must not create extra fragments");
    Console.WriteLine("PASS: open terrain edge clipping intervals");return;
}

var control = new ControlState();
Check(!control.RequestOwner(false, true), "An attack must retain its controller until its hit window ends");
Check(control.TryAirJump(true, false), "The first unlocked air jump must succeed");
for (int i = 0; i < 100; i++)
{
    control.RequestOwner(i % 2 == 0, false);
    Check(!control.TryAirJump(true, false), "Item switches must not restore an air jump");
}
control.Land();
Check(control.TryAirJump(true, false), "Landing must restore the air jump");
Check(!control.TryAirJump(false, false), "A locked ability cannot be used");
Check(DamageRules.Explosion(4, 0, 1) == 57, "TNT centre damage must follow the Minecraft formula");
Check(DamageRules.Explosion(4, 9, 1) == 0, "An entity outside the blast must not be hurt");
Check(DamageRules.Explosion(4, 1, 0) == 1, "Vanilla retains the in-range +1 damage term at zero exposure");
Check(DamageRules.Explosion(4, float.NaN, 1) == 0, "Non-finite positions must not become damage");
Check(DamageRules.Enemy(7) == 21 && DamageRules.Player(5) == 2, "Damage scales must match the agreed values");
var gate = new EventGate(100);
Check(gate.Accept(100, 2, 3, 1, 2, 3), "A fresh event must be accepted");
Check(!gate.Accept(100, 2, 3, 1, 2, 3), "A duplicate explosion must not be accepted twice");
Check(!gate.Accept(100, 2, 2, 2, 2, 3), "An event from the previous scene epoch must be rejected");
Check(!gate.Accept(99, 2, 3, 2, 2, 3), "An event from a previous process session must be rejected");
Check(gate.Accept(100, 2, 3, 3, 2, 3), "A subsequent valid explosion must still be accepted");
Check(gate.Accept(100, 2, 4, 1, 2, 4), "A restarted peer may restart event IDs only in a new epoch");
Check(!gate.Accept(100, 2, 3, 99, 2, 4), "A queued old event cannot consume the new epoch's sequence");
Check(gate.Accept(100, 2, 4, 2, 2, 4), "Old-epoch rejection must preserve fresh events");
Console.WriteLine("PASS: controller handoff, air-jump budget, damage scaling, event identity");
var source = HollowCraft.World.Clip.FromTriangle(0, 0, 0, 4, 0, 0, 0, 4, 0);
var pieces = new System.Collections.Generic.List<System.Collections.Generic.List<HollowCraft.World.Clip.Vert>>();
var box = new HollowCraft.World.Clip.Box { LoX = 0, LoY = 0, LoZ = -1, HiX = 1, HiY = 1, HiZ = 1 };
Check(HollowCraft.World.Clip.Subtract(source, new() { box }, pieces), "The terrain triangle must be cut");
double area = 0;
foreach (var piece in pieces)
{
    area += HollowCraft.World.Clip.Area2(piece) / 2;
    foreach (var vertex in piece)
        Check(Math.Abs(vertex.B0 + vertex.B1 + vertex.B2 - 1) < 1e-6, "Cut vertices must preserve UV interpolation weights");
}
Check(Math.Abs(area - 7) < 1e-6, "Clipping must remove exactly the one-square-unit intersection");
Console.WriteLine("PASS: terrain clipping area and UV barycentric preservation");
string checkpointTest = System.IO.Path.Combine(System.IO.Path.GetTempPath(), "hollowcraft-check-" + Guid.NewGuid().ToString("N"));
System.IO.Directory.CreateDirectory(checkpointTest);
try
{
    string snapshot = System.IO.Path.Combine(checkpointTest, "snapshot.dat"), active = System.IO.Path.Combine(checkpointTest, "active.dat");
    CheckpointFiles.Write(snapshot, new byte[] { 1, 2, 3 });
    string hash = CheckpointFiles.Hash(snapshot);
    CheckpointFiles.Write(active, new byte[] { 9 });
    CheckpointFiles.Restore(snapshot, active, hash);
    Check(System.IO.File.ReadAllBytes(active)[2] == 3, "Committed checkpoint must restore the matching save");
    CheckpointFiles.Write(snapshot, new byte[] { 8 });
    try { CheckpointFiles.Restore(snapshot, active, hash); throw new Exception("Corrupt snapshot was accepted"); }
    catch (System.IO.InvalidDataException) { }
    Check(System.IO.File.ReadAllBytes(active)[2] == 3, "Failed restore must preserve the existing save");
    try { CheckpointFiles.DirectoryFor(checkpointTest, 1, "../escape"); throw new Exception("Traversal was accepted"); }
    catch (System.IO.InvalidDataException) { }
}
finally { System.IO.Directory.Delete(checkpointTest, true); }
Console.WriteLine("PASS: atomic save recovery, checksum rejection and checkpoint path validation");
