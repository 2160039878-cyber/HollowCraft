using System;
using System.Collections.Generic;
using UnityEngine;

namespace HollowCraft.World
{
    internal sealed class TerrainCutter
    {
        private sealed class Target
        {
            public Collider2D Collider;
            public Renderer Renderer;
            public Mesh Original, Cut;
            public MeshFilter Filter;
            public Bounds Bounds;
            public GameObject Replacement;
            public bool OwnsOriginal;
        }
        private sealed class Prepared
        {
            public Target Target;
            public Mesh Mesh;
            public GameObject Replacement;
        }

        public static readonly TerrainCutter Instance = new TerrainCutter();
        private readonly MeshSlice slicer = new MeshSlice();
        private readonly Dictionary<(int, int), List<Target>> regions = new Dictionary<(int, int), List<Target>>();
        private readonly List<Target> targets = new List<Target>();
        private readonly HashSet<Target> dirty = new HashSet<Target>();
        private readonly Queue<Target> pending = new Queue<Target>();
        private readonly List<Prepared> staged = new List<Prepared>();
        private readonly List<(int x, int y, int z)> changed = new List<(int, int, int)>();
        private bool indexed;
        public int CutCount { get; private set; }
        public int CutColliderCount { get; private set; }
        public int Pending => pending.Count + dirty.Count;
        public event Action Committed;

        public static bool Diggable(Collider2D collider)
        {
            if (collider == null || collider.isTrigger || collider.gameObject.layer != LayerMask.NameToLayer("Terrain")
                || collider.GetComponentInParent<HollowCraftGeometry>() != null
                || (collider.attachedRigidbody != null && collider.attachedRigidbody.bodyType != RigidbodyType2D.Static)) return false;
            return !Protected(collider.transform);
        }

        private static bool Protected(Transform transform)
        {
            for (Transform node = transform; node != null; node = node.parent)
            {
                string name = node.name.ToLowerInvariant();
                if (name.Contains("bounds") || name.Contains("boundary") || name.Contains("scene border")
                    || name.Contains("transition") || name.Contains("bench") || name.Contains("respawn")
                    || name.Contains("gate") || name.Contains("door")) return true;
                if (node.GetComponent<TransitionPoint>() != null || node.GetComponent<HealthManager>() != null) return true;
            }
            return false;
        }

        public void Clear()
        {
            foreach (Prepared item in staged) DestroyPrepared(item);
            staged.Clear(); pending.Clear(); dirty.Clear(); changed.Clear(); regions.Clear();
            foreach (Target target in targets)
            {
                if (target.Collider != null) target.Collider.enabled = true;
                if (target.Renderer != null) target.Renderer.enabled = true;
                if (target.Filter != null && target.Original != null) target.Filter.sharedMesh = target.Original;
                if (target.Replacement != null) { target.Replacement.SetActive(false); UnityEngine.Object.Destroy(target.Replacement); }
                if (target.Cut != null) UnityEngine.Object.Destroy(target.Cut);
                if (target.OwnsOriginal && target.Original != null) UnityEngine.Object.Destroy(target.Original);
            }
            targets.Clear(); slicer.Clear(); indexed = false; CutCount = CutColliderCount = 0;
            Physics2D.SyncTransforms();
        }

        public void AddCutOriginals(Bounds bounds, List<Collider2D> output)
        {
            foreach (Target target in targets)
                if (target.Collider != null && !target.Collider.enabled && target.Bounds.Intersects(bounds)) output.Add(target.Collider);
        }

        private void Index()
        {
            if (indexed) return;
            indexed = true;
            foreach (Collider2D collider in UnityEngine.Object.FindObjectsOfType<Collider2D>())
                if (collider.enabled && Diggable(collider)) Add(new Target { Collider = collider, Bounds = collider.bounds });
            foreach (Renderer renderer in UnityEngine.Object.FindObjectsOfType<Renderer>())
            {
                Rigidbody2D body = renderer.GetComponentInParent<Rigidbody2D>();
                if (!renderer.enabled || renderer.GetComponentInParent<HollowCraftGeometry>() != null
                    || renderer.GetComponentInParent<HealthManager>() != null || renderer.GetComponentInParent<HeroController>() != null
                    || (body != null && body.bodyType != RigidbodyType2D.Static) || Protected(renderer.transform)) continue;
                string name = renderer.name.ToLowerInvariant();
                // TileMap chunks and black interior fills also cover solid terrain, despite lacking land-art names.
                bool land = renderer.gameObject.layer == LayerMask.NameToLayer("Terrain")
                    || name.Contains("_land_") || name.Contains("terrain") || name.Contains("floor")
                    || name.Contains("ceiling") || name.Contains("roof") || name.Contains("wall") || name.StartsWith("black_solid",StringComparison.Ordinal);
                if (!land || name.Contains("bg_") || name.Contains("background") || name.Contains("_fg_")
                    || name.Contains("wallpaper")) continue;
                if (!(renderer is SpriteRenderer) && renderer.GetComponent<MeshFilter>() == null) continue;
                Add(new Target { Renderer = renderer, Filter = renderer.GetComponent<MeshFilter>(), Bounds = renderer.bounds });
            }
            Log.Info($"Terrain cut index: {targets.Count} static collision/art objects");
        }

        private void Add(Target target)
        {
            targets.Add(target);
            Vector3 lo = Coords.ToMcF(target.Bounds.min), hi = Coords.ToMcF(target.Bounds.max);
            for (int x = Mathf.FloorToInt(lo.x / 16); x <= Mathf.FloorToInt(hi.x / 16); x++)
                for (int y = Mathf.FloorToInt(lo.y / 16); y <= Mathf.FloorToInt(hi.y / 16); y++)
                {
                    if (!regions.TryGetValue((x, y), out var list)) regions[(x, y)] = list = new List<Target>();
                    list.Add(target);
                }
        }

        public void Frame()
        {
            changed.Clear(); DugBlocks.TakeChanged(changed);
            if (changed.Count > 0)
            {
                Index();
                int plane = (int)Math.Floor(Coords.PlaneZ);
                foreach (var cell in changed)
                {
                    if (cell.z != plane || !regions.TryGetValue((cell.x >> 4, cell.y >> 4), out var list)) continue;
                    Vector3 point = Coords.ToUnity(cell.x + .5, cell.y + .5, Coords.PlaneZ);
                    foreach (Target target in list)
                    {
                        Bounds bounds = target.Bounds; bounds.Expand(1 / Coords.K);
                        if (point.x >= bounds.min.x && point.x <= bounds.max.x && point.y >= bounds.min.y && point.y <= bounds.max.y) dirty.Add(target);
                    }
                }
                // A newer dig snapshot supersedes the uncommitted batch; no half-applied holes.
                foreach (Prepared item in staged) { dirty.Add(item.Target); DestroyPrepared(item); }
                staged.Clear();
                while (pending.Count > 0) dirty.Add(pending.Dequeue());
            }
            if (pending.Count == 0 && dirty.Count > 0)
            {
                foreach (Target target in dirty) pending.Enqueue(target);
                dirty.Clear();
            }
            var clock = System.Diagnostics.Stopwatch.StartNew();
            while (pending.Count > 0 && clock.Elapsed.TotalMilliseconds < 3)
                staged.Add(Prepare(pending.Dequeue()));
            if (pending.Count > 0 || staged.Count == 0) return;
            // Commit every renderer and Collider2D in the same update, before the next physics step.
            foreach (Prepared item in staged) Commit(item);
            staged.Clear(); Physics2D.SyncTransforms(); Committed?.Invoke();
            CutCount = CutColliderCount = 0;
            foreach (Target target in targets) if (target.Cut != null || target.Replacement != null)
            {
                CutCount++;
                if (target.Collider != null) CutColliderCount++;
            }
            Log.Info($"Terrain cut committed: {CutCount - CutColliderCount} renderers, {CutColliderCount} colliders");
        }

        private Prepared Prepare(Target target)
        {
            var item = new Prepared { Target = target };
            if (target.Collider == null && target.Renderer == null) return item;
            Vector3 lo = Coords.ToMcF(target.Bounds.min), hi = Coords.ToMcF(target.Bounds.max);
            var cells = new List<(int x, int y, int z)>();
            DugBlocks.Collect(lo.x, lo.y, (float)Coords.PlaneZ, hi.x, hi.y, (float)Coords.PlaneZ, cells);
            if (cells.Count == 0) return item;
            List<Clip.Box> boxes = Clip.Merge(cells);
            for (int i = 0; i < boxes.Count; i++) { var b = boxes[i]; b.LoZ = -1e7f; b.HiZ = 1e7f; boxes[i] = b; }
            if(target.Collider is EdgeCollider2D edge) return PrepareEdge(target,edge,boxes);
            if (target.Original == null) ReadOriginal(target);
            if (target.Original == null) throw new InvalidOperationException("Cannot cut terrain " + (target.Collider != null ? target.Collider.name : target.Renderer.name));
            Matrix4x4 matrix = target.Collider != null ? Matrix4x4.identity : target.Renderer.transform.localToWorldMatrix;
            item.Mesh = slicer.Build(target.Original, matrix, boxes);
            if (item.Mesh == null) return item;
            if (target.Collider != null)
            {
                var go = item.Replacement = new GameObject("HollowCraft cut collision") { layer = target.Collider.gameObject.layer };
                go.SetActive(false); go.AddComponent<HollowCraftGeometry>();
                go.AddComponent<HollowCraftTerrainPiece>().Original = target.Collider;
                var body = go.AddComponent<Rigidbody2D>(); body.bodyType = RigidbodyType2D.Static;
                var composite = go.AddComponent<CompositeCollider2D>();
                composite.geometryType = CompositeCollider2D.GeometryType.Polygons;
                composite.generationType = CompositeCollider2D.GenerationType.Manual;
                composite.sharedMaterial = target.Collider.sharedMaterial;
                composite.vertexDistance = .0001f;
                Vector3[] vertices = item.Mesh.vertices; int[] triangles = item.Mesh.triangles;
                if (triangles.Length > 0)
                {
                    var polygon = go.AddComponent<PolygonCollider2D>();
                    polygon.compositeOperation = Collider2D.CompositeOperation.Merge;
                    polygon.pathCount = triangles.Length / 3;
                    for (int i = 0; i < triangles.Length; i += 3)
                        polygon.SetPath(i / 3, new Vector2[] { vertices[triangles[i]], vertices[triangles[i + 1]], vertices[triangles[i + 2]] });
                }
            }
            else if (target.Renderer is SpriteRenderer sprite)
            {
                var go = item.Replacement = new GameObject("HollowCraft cut sprite");
                go.SetActive(false); go.AddComponent<HollowCraftGeometry>();
                go.transform.SetParent(sprite.transform, false);
                go.AddComponent<MeshFilter>().sharedMesh = item.Mesh;
                var renderer = go.AddComponent<MeshRenderer>();
                renderer.sharedMaterials = sprite.sharedMaterials;
                renderer.sortingLayerID = sprite.sortingLayerID; renderer.sortingOrder = sprite.sortingOrder;
                var properties = new MaterialPropertyBlock(); sprite.GetPropertyBlock(properties);
                properties.SetTexture("_MainTex", sprite.sprite.texture);
                properties.SetColor("_RendererColor", Color.white);
                renderer.SetPropertyBlock(properties);
            }
            return item;
        }

        private static Prepared PrepareEdge(Target target,EdgeCollider2D edge,List<Clip.Box> boxes)
        {
            var points=edge.points;
            if(points.Length<2) return new Prepared {Target=target};
            var go=new GameObject("HollowCraft cut edge") {layer=edge.gameObject.layer};
            go.SetActive(false);go.transform.SetParent(edge.transform,false);
            go.AddComponent<HollowCraftGeometry>();go.AddComponent<HollowCraftTerrainPiece>().Original=edge;
            var result=new Prepared {Target=target,Replacement=go};
            if(points.Length>=4 && (points[0]-points[points.Length-1]).sqrMagnitude<1e-8f)
            {
                // CreateMesh would convexify a closed EdgeCollider. Native polygon composition preserves its concavity.
                var body=go.AddComponent<Rigidbody2D>();body.bodyType=RigidbodyType2D.Static;
                var composite=go.AddComponent<CompositeCollider2D>();
                composite.geometryType=CompositeCollider2D.GeometryType.Outlines;
                composite.generationType=CompositeCollider2D.GenerationType.Manual;
                composite.vertexDistance=.0001f;composite.edgeRadius=edge.edgeRadius;composite.sharedMaterial=edge.sharedMaterial;
                var original=go.AddComponent<PolygonCollider2D>();original.compositeOperation=Collider2D.CompositeOperation.Merge;
                original.compositeOrder=0;original.offset=edge.offset;
                var outline=new Vector2[points.Length-1];Array.Copy(points,outline,outline.Length);original.points=outline;
                double area=0;for(int i=0;i<outline.Length;i++) {var a=outline[i];var b=outline[(i+1)%outline.Length];area+=(double)a.x*b.y-(double)b.x*a.y;}
                int order=1;
                foreach(var box in boxes)
                {
                    var cutter=go.AddComponent<PolygonCollider2D>();cutter.compositeOrder=order++;
                    // Clockwise tile contours bound empty pockets; excavation expands those pockets.
                    cutter.compositeOperation=area>=0 ? Collider2D.CompositeOperation.Difference : Collider2D.CompositeOperation.Merge;
                    cutter.points=new[]{
                        (Vector2)edge.transform.InverseTransformPoint(Coords.ToUnity(box.LoX,box.LoY,Coords.PlaneZ)),
                        (Vector2)edge.transform.InverseTransformPoint(Coords.ToUnity(box.HiX,box.LoY,Coords.PlaneZ)),
                        (Vector2)edge.transform.InverseTransformPoint(Coords.ToUnity(box.HiX,box.HiY,Coords.PlaneZ)),
                        (Vector2)edge.transform.InverseTransformPoint(Coords.ToUnity(box.LoX,box.HiY,Coords.PlaneZ))};
                }
            }
            else
            {
                var pieces=new List<(float From,float To)>();var run=new List<Vector2>();
                void Flush()
                {
                    if(run.Count>=2)
                    {
                        var fragment=go.AddComponent<EdgeCollider2D>();fragment.points=run.ToArray();fragment.offset=edge.offset;
                        fragment.edgeRadius=edge.edgeRadius;fragment.sharedMaterial=edge.sharedMaterial;
                        fragment.useAdjacentStartPoint=edge.useAdjacentStartPoint && (run[0]-points[0]).sqrMagnitude<1e-8f;
                        fragment.adjacentStartPoint=edge.adjacentStartPoint;
                        fragment.useAdjacentEndPoint=edge.useAdjacentEndPoint && (run[run.Count-1]-points[points.Length-1]).sqrMagnitude<1e-8f;
                        fragment.adjacentEndPoint=edge.adjacentEndPoint;
                    }
                    run.Clear();
                }
                for(int i=0;i+1<points.Length;i++)
                {
                    Vector3 a=Coords.ToMcF(edge.transform.TransformPoint(points[i]+edge.offset));
                    Vector3 b=Coords.ToMcF(edge.transform.TransformPoint(points[i+1]+edge.offset));
                    Clip.SubtractSegment(a.x,a.y,b.x,b.y,boxes,pieces);
                    foreach(var part in pieces)
                    {
                        Vector2 start=Vector2.Lerp(points[i],points[i+1],part.From),end=Vector2.Lerp(points[i],points[i+1],part.To);
                        if(run.Count!=0 && (run[run.Count-1]-start).sqrMagnitude>1e-8f) Flush();
                        if(run.Count==0) run.Add(start);run.Add(end);
                    }
                }
                Flush();
            }
            return result;
        }

        private static void ReadOriginal(Target target)
        {
            if (target.Collider != null)
            {
                bool hasBody = target.Collider.attachedRigidbody != null;
                target.Original = target.Collider.CreateMesh(hasBody, hasBody); target.OwnsOriginal = true;
                if (target.Original != null && Vector2.Distance(target.Original.bounds.center, target.Bounds.center) > .02f)
                    throw new InvalidOperationException("Native terrain mesh is not in world coordinates: " + target.Collider.name);
                return;
            }
            if (target.Renderer is SpriteRenderer sprite)
            {
                var mesh = new Mesh { name = sprite.sprite.name + " (source)" };
                Vector2[] points = sprite.sprite.vertices; var vertices = new Vector3[points.Length];
                var colors = new Color[points.Length];
                for (int i = 0; i < points.Length; i++)
                {
                    vertices[i] = new Vector3(points[i].x * (sprite.flipX ? -1 : 1), points[i].y * (sprite.flipY ? -1 : 1));
                    colors[i] = sprite.color;
                }
                ushort[] source = sprite.sprite.triangles; var triangles = new int[source.Length];
                for (int i = 0; i < source.Length; i++) triangles[i] = source[i];
                mesh.vertices = vertices; mesh.uv = sprite.sprite.uv; mesh.colors = colors; mesh.triangles = triangles;
                mesh.RecalculateBounds(); target.Original = mesh; target.OwnsOriginal = true;
            }
            else target.Original = target.Filter.sharedMesh;
        }

        private static void Commit(Prepared item)
        {
            Target target = item.Target;
            if (target.Replacement != null) { target.Replacement.SetActive(false); UnityEngine.Object.Destroy(target.Replacement); }
            if (target.Cut != null) UnityEngine.Object.Destroy(target.Cut);
            target.Cut = item.Mesh; target.Replacement = item.Replacement;
            if (target.Collider != null) target.Collider.enabled = item.Replacement == null;
            else if (target.Renderer is SpriteRenderer) target.Renderer.enabled = item.Mesh == null;
            // A cleared dig snapshot may arrive before this target has ever cached its original mesh.
            else if (target.Filter != null && (item.Mesh != null || target.Original != null))
                target.Filter.sharedMesh = item.Mesh != null ? item.Mesh : target.Original;
            if (item.Replacement != null)
            {
                item.Replacement.SetActive(true);
                item.Replacement.GetComponent<CompositeCollider2D>()?.GenerateGeometry();
            }
        }
        private static void DestroyPrepared(Prepared item)
        {
            if (item.Mesh != null) UnityEngine.Object.Destroy(item.Mesh);
            if (item.Replacement != null) UnityEngine.Object.Destroy(item.Replacement);
        }
    }

    internal sealed class HollowCraftTerrainPiece : MonoBehaviour
    {
        public Collider2D Original;
    }
}
