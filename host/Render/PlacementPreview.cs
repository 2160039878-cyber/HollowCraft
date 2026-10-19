using System;
using HollowCraft.Link;
using UnityEngine;

namespace HollowCraft.Render
{
    internal sealed class PlacementPreview
    {
        private readonly byte[] entities = new byte[Proto.WeRecords + Proto.MaxWorldEntities * Proto.WorldEntityBytes];
        private readonly Vector3[] points = new Vector3[4];
        private LineRenderer line;

        public void Frame(bool visible)
        {
            if (line == null)
            {
                var node = new GameObject("HollowCraft placement preview");
                node.transform.SetParent(BlockRenderer.Instance.Root.transform, false);
                line = node.AddComponent<LineRenderer>();
                line.sharedMaterial = Materials.Lines();
                line.useWorldSpace = true; line.loop = true; line.positionCount = 4; line.widthMultiplier = .025f;
            }
            line.enabled = false;
            if (!visible || SharedLink.Instance.ReadWorldEntities(entities) < 0) return;
            int kind = BitConverter.ToInt32(entities, (int)Proto.WeHasSelection);
            if (kind < 1 || kind > 3) return;
            float x0 = BitConverter.ToSingle(entities, 12), y0 = BitConverter.ToSingle(entities, 16), z = BitConverter.ToSingle(entities, 32);
            float x1 = BitConverter.ToSingle(entities, 24), y1 = BitConverter.ToSingle(entities, 28);
            if (!DamageRules.Finite(x0) || !DamageRules.Finite(y0) || !DamageRules.Finite(z) || !DamageRules.Finite(x1)
                || !DamageRules.Finite(y1) || x1 <= x0 || y1 <= y0 || x1 - x0 > 4 || y1 - y0 > 4) return;
            points[0] = Coords.ToUnity(x0, y0, z + .02f); points[1] = Coords.ToUnity(x1, y0, z + .02f);
            points[2] = Coords.ToUnity(x1, y1, z + .02f); points[3] = Coords.ToUnity(x0, y1, z + .02f);
            line.startColor = line.endColor = kind == 2 ? new Color(.3f, 1, .6f) : kind == 3 ? new Color(1, .3f, .2f) : Color.white;
            line.SetPositions(points); line.enabled = true;
        }
    }
}
