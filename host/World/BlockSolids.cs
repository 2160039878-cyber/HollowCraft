using System;
using System.Collections.Generic;
using UnityEngine;

namespace HollowCraft.World
{
    internal sealed unsafe class BlockSolids
    {
        public static readonly BlockSolids Instance = new BlockSolids();
        private readonly Dictionary<long, (GameObject go, ulong hash)> sections = new Dictionary<long, (GameObject, ulong)>();
        public void Clear()
        {
            foreach (var value in sections.Values) if (value.go != null) UnityEngine.Object.Destroy(value.go);
            sections.Clear();
        }
        public void OnSolids(byte* data, uint bytes)
        {
            if (bytes < 16) throw new InvalidOperationException("Truncated collision section");
            int sx = *(int*)data, sy = *(int*)(data + 4), sz = *(int*)(data + 8);
            uint count = *(uint*)(data + 12);
            if (count > 65536 || bytes != 16 + (ulong)count * 24) throw new InvalidOperationException("Invalid collision shape count");
            double plane = Coords.PlaneZ - sz * 16;
            if (plane < -1 || plane > 17) return;
            ulong hash = 14695981039346656037;
            for (int i = 16; i < bytes; i++) hash = unchecked((hash ^ data[i]) * 1099511628211);
            long key = Clip.Key(sx, sy, sz);
            if (sections.TryGetValue(key, out var previous) && previous.hash == hash) return;
            var paths = new List<Vector2[]>();
            for (int i = 0; i < count; i++)
            {
                float* box = (float*)(data + 16 + i * 24);
                for (int a = 0; a < 6; a++) if (!DamageRules.Finite(box[a]) || box[a] < -16 || box[a] > 32)
                    throw new InvalidOperationException("Invalid block collision coordinate");
                if (box[0] >= box[3] || box[1] >= box[4] || box[2] >= box[5]) throw new InvalidOperationException("Empty collision shape");
                if (box[2] > plane + .3 || box[5] < plane - .3) continue;
                float x0 = box[0] / Coords.K, y0 = box[1] / Coords.K, x1 = box[3] / Coords.K, y1 = box[4] / Coords.K;
                paths.Add(new[] { new Vector2(x0, y0), new Vector2(x1, y0), new Vector2(x1, y1), new Vector2(x0, y1) });
            }
            GameObject go = null;
            if (paths.Count > 0)
            {
                int layer = LayerMask.NameToLayer("Terrain");
                if (layer < 0) throw new InvalidOperationException("Terrain collision layer is unavailable");
                go = new GameObject($"HollowCraft blocks {sx}/{sy}/{sz}") { layer = layer };
                go.SetActive(false); go.AddComponent<HollowCraftGeometry>();
                UnityEngine.Object.DontDestroyOnLoad(go);
                go.transform.position = Coords.ToUnity(sx * 16, sy * 16, Coords.PlaneZ);
                go.AddComponent<Rigidbody2D>().bodyType = RigidbodyType2D.Static;
                var composite = go.AddComponent<CompositeCollider2D>();
                composite.geometryType = CompositeCollider2D.GeometryType.Polygons;
                composite.generationType = CompositeCollider2D.GenerationType.Manual;
                var polygon = go.AddComponent<PolygonCollider2D>();
                polygon.compositeOperation = Collider2D.CompositeOperation.Merge;
                polygon.pathCount = paths.Count;
                for (int i = 0; i < paths.Count; i++) polygon.SetPath(i, paths[i]);
                go.SetActive(true); composite.GenerateGeometry();
            }
            if (previous.go != null) { previous.go.SetActive(false); UnityEngine.Object.Destroy(previous.go); }
            sections[key] = (go, hash);
        }
    }

    internal sealed class HollowCraftGeometry : MonoBehaviour { }
}
