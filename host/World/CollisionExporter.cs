using System;
using System.Collections.Generic;
using UnityEngine;
using HollowCraft.Link;

namespace HollowCraft.World
{
    internal sealed class CollisionExporter
    {
        private readonly CollisionWorker worker = new CollisionWorker();
        private readonly Collider2D[] hits = new Collider2D[2048];
        private readonly Dictionary<long, float> sent = new Dictionary<long, float>();
        private readonly List<Vector2Int> offsets = new List<Vector2Int>();
        private readonly List<Vector2> points = new List<Vector2>();
        private readonly List<Collider2D> originals = new List<Collider2D>();
        private uint epoch;
        private int terrainMask;
        public int Pending => worker.Pending;

        public CollisionExporter()
        {
            terrainMask = LayerMask.GetMask("Terrain");
            if (terrainMask == 0) throw new InvalidOperationException("Terrain layer was not found");
            for (int x = -5; x <= 5; x++) for (int y = -4; y <= 4; y++) offsets.Add(new Vector2Int(x, y));
            offsets.Sort((a, b) => a.sqrMagnitude.CompareTo(b.sqrMagnitude));
            worker.Start();
        }

        public void Stop() => worker.Stop();
        public void Reset(uint value) { epoch = value; sent.Clear(); worker.Reset(value); }
        public void Invalidate() => sent.Clear();

        public void Update(Vector3 mcPosition)
        {
            if (worker.Pending > 12) return;
            int rx = Mathf.FloorToInt(mcPosition.x / 8), ry = Mathf.FloorToInt(mcPosition.y / 8);
            int rz = (int)Math.Floor(Coords.PlaneZ / 8);
            float now = Time.realtimeSinceStartup;
            int count = 0;
            var clock = System.Diagnostics.Stopwatch.StartNew();
            foreach (Vector2Int offset in offsets)
            {
                int x = rx + offset.x, y = ry + offset.y;
                long key = Clip.Key(x, y, rz);
                bool nearby = offset.sqrMagnitude <= 2;
                if (sent.TryGetValue(key, out float previous) && (!nearby || now - previous < .5f)) continue;
                Harvest(x, y, rz);
                sent[key] = now;
                if (++count >= 3 || clock.Elapsed.TotalMilliseconds > 2) break;
            }
        }

        private void Harvest(int rx, int ry, int rz)
        {
            var job = new CollisionJob { Rx = rx, Ry = ry, Rz = rz, Epoch = epoch };
            Vector3 centre = Coords.ToUnity(rx * 8 + 4, ry * 8 + 4, Coords.PlaneZ);
            int count = Physics2D.OverlapBoxNonAlloc(centre, Vector2.one * (10 / Coords.K), 0, hits, terrainMask);
            if (count == hits.Length) throw new InvalidOperationException("Collision query capacity exceeded");
            originals.Clear();
            for (int i = 0; i < count; i++) if (hits[i] != null && hits[i].enabled) originals.Add(hits[i]);
            TerrainCutter.Instance.AddCutOriginals(new Bounds(centre, new Vector3(10 / Coords.K, 10 / Coords.K, 100)), originals);
            foreach (Collider2D collider in originals)
            {
                if (collider == null || collider.isTrigger) continue;
                var cut = collider.GetComponent<HollowCraftTerrainPiece>();
                if (collider.GetComponentInParent<HollowCraftGeometry>() != null && (cut == null || !(collider is CompositeCollider2D))) continue;
                bool diggable = cut != null || TerrainCutter.Diggable(collider);
                uint flags = (diggable ? Proto.TriDiggable : 0) | ((uint)Proto.DigStone << Proto.TriMaterialShift);
                if (!collider.enabled) flags |= Proto.TriGhost;
                if (collider is BoxCollider2D box)
                {
                    Vector2 h = box.size * .5f, o = box.offset;
                    points.Clear();
                    points.Add(o + new Vector2(-h.x, -h.y)); points.Add(o + new Vector2(h.x, -h.y));
                    points.Add(o + new Vector2(h.x, h.y)); points.Add(o + new Vector2(-h.x, h.y));
                    EmitPath(job, points, box.transform, true, flags, box);
                }
                else if (collider is PolygonCollider2D polygon)
                {
                    for (int p = 0; p < polygon.pathCount; p++)
                    {
                        points.Clear();
                        foreach (Vector2 point in polygon.GetPath(p)) points.Add(point + polygon.offset);
                        EmitPath(job, points, polygon.transform, true, flags, polygon);
                    }
                }
                else if (collider is EdgeCollider2D edge)
                {
                    points.Clear();
                    foreach (Vector2 point in edge.points) points.Add(point + edge.offset);
                    EmitPath(job, points, edge.transform, false, flags);
                }
                else if (collider is CompositeCollider2D composite)
                {
                    for (int p = 0; p < composite.pathCount; p++)
                    {
                        var path = new Vector2[composite.GetPathPointCount(p)];
                        composite.GetPath(p, path);
                        points.Clear();
                        foreach (Vector2 point in path) points.Add(point + composite.offset);
                        bool closed = composite.geometryType == CompositeCollider2D.GeometryType.Polygons ||
                            (path.Length > 2 && (path[0] - path[path.Length - 1]).sqrMagnitude < 1e-8f);
                        EmitPath(job, points, composite.transform, closed, flags, composite);
                    }
                }
                else
                {
                    EmitMeshBoundary(job, collider, flags);
                }
            }
            worker.Enqueue(job);
        }

        private static void EmitPath(CollisionJob job, IList<Vector2> path, Transform transform, bool closed, uint flags, Collider2D solid = null)
        {
            double area = 0;
            if (closed) for (int i = 0; i < path.Count; i++)
            {
                Vector3 a = transform.TransformPoint(path[i]), b = transform.TransformPoint(path[(i + 1) % path.Count]);
                area += a.x * (double)b.y - b.x * (double)a.y;
            }
            // A mirrored Unity transform must not turn open air into the solid side of a wall.
            for (int i = 0; i < path.Count - (closed ? 0 : 1); i++)
            {
                Vector3 a = transform.TransformPoint(path[i]), b = transform.TransformPoint(path[(i + 1) % path.Count]);
                bool reverse = closed && area < 0;
                if (solid != null && solid.enabled)
                {
                    Vector2 middle = (a + b) * .5f;
                    Vector2 normal = new Vector2(b.y - a.y, a.x - b.x).normalized * .001f;
                    bool outInside = solid.OverlapPoint(middle + normal), inInside = solid.OverlapPoint(middle - normal);
                    if (outInside != inInside) reverse = outInside;
                }
                if (reverse) EmitEdge(job, b, a, flags); else EmitEdge(job, a, b, flags);
            }
        }

        private static void EmitEdge(CollisionJob job, Vector3 a, Vector3 b, uint flags)
        {
            if ((a - b).sqrMagnitude < 1e-10f) return;
            float ax = (float)(a.x * Coords.K + Coords.OffsetX), ay = a.y * Coords.K;
            float bx = (float)(b.x * Coords.K + Coords.OffsetX), by = b.y * Coords.K;
            float z0 = (float)Coords.PlaneZ - 3, z1 = (float)Coords.PlaneZ + 3;
            job.Tris.Add(new Tri(ax, ay, z0, bx, by, z0, bx, by, z1, flags));
            job.Tris.Add(new Tri(ax, ay, z0, bx, by, z1, ax, ay, z1, flags));
        }

        private static void EmitMeshBoundary(CollisionJob job, Collider2D collider, uint flags)
        {
            bool hasBody = collider.attachedRigidbody != null;
            Mesh mesh = collider.CreateMesh(hasBody, hasBody);
            if (mesh == null) throw new InvalidOperationException("Unsupported collider: " + collider.GetType().Name);
            try
            {
                Vector3[] vertices = mesh.vertices;
                int[] triangles = mesh.triangles;
                var edges = new Dictionary<(int, int), (int count, int a, int b)>();
                for (int i = 0; i < triangles.Length; i += 3)
                {
                    Vector3 p = vertices[triangles[i]], q = vertices[triangles[i + 1]], r = vertices[triangles[i + 2]];
                    bool reverse = Vector3.Cross(q - p, r - p).z < 0;
                    for (int j = 0; j < 3; j++)
                    {
                        int a = triangles[i + j], b = triangles[i + (j + 1) % 3];
                        var key = a < b ? (a, b) : (b, a);
                        edges.TryGetValue(key, out var edge); edges[key] = (edge.count + 1, reverse ? b : a, reverse ? a : b);
                    }
                }
                Bounds bounds = mesh.bounds;
                if (Vector2.Distance(bounds.center, collider.bounds.center) > .02f)
                    throw new InvalidOperationException("Collider mesh coordinates are not world-space: " + collider.GetType().Name);
                foreach (var edge in edges.Values) if (edge.count == 1)
                    EmitEdge(job, vertices[edge.a], vertices[edge.b], flags);
            }
            finally { UnityEngine.Object.Destroy(mesh); }
        }
    }
}
