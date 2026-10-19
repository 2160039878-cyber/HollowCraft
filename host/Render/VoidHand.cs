using System;
using System.Collections.Generic;
using Newtonsoft.Json.Linq;
using UnityEngine;

namespace HollowCraft.Render
{
    // The native hand shares its atlas quad with Radiance's eye and flash.
    internal sealed class VoidHand : IDisposable
    {
        private static readonly JToken Geometry = SteveRig.ReadJson("void-hand-geometry.json")["sprites"];
        private static readonly Dictionary<string, Texture2D> Textures = new Dictionary<string, Texture2D>();
        private readonly tk2dSpriteAnimator animator;
        private readonly tk2dBaseSprite sprite;
        private readonly Renderer source;
        private readonly MeshFilter sourceMesh;
        private readonly GameObject effects;
        private readonly MeshRenderer effectRenderer;
        private readonly Mesh mesh;
        private readonly MaterialPropertyBlock properties = new MaterialPropertyBlock();
        private readonly List<Vector3> quad = new List<Vector3>(4);
        private readonly List<Color32> sourceColors = new List<Color32>(4);
        private readonly Dictionary<string, Material> materials = new Dictionary<string, Material>();
        private static readonly Vector2[] EffectUv = { Vector2.zero, Vector2.right, Vector2.up, Vector2.one };
        private SteveRig arm;
        private string lastSprite;
        private Vector3 lastScale;
        private Color32 lastColor;
        public VoidHand(tk2dSpriteAnimator animator)
        {
            this.animator = animator; sprite = animator.Sprite;
            source = sprite.GetComponent<Renderer>(); sourceMesh = sprite.GetComponent<MeshFilter>();
            effects = new GameObject("HollowCraft retained Radiance eye");
            effects.transform.SetParent(sprite.transform, false);
            mesh = new Mesh { name = "Native eye and flash regions" }; mesh.MarkDynamic();
            effects.AddComponent<MeshFilter>().sharedMesh = mesh;
            effectRenderer = effects.AddComponent<MeshRenderer>(); effects.SetActive(false);
        }
        public bool Frame(bool replace)
        {
            bool visible = replace && animator != null && sprite != null && source != null
                && source.enabled && sprite.gameObject.activeInHierarchy;
            string name = visible ? sprite.GetCurrentSpriteDef()?.name : null;
            JToken geometry = name == null ? null : Geometry[name];
            visible &= geometry != null && sourceMesh != null && sourceMesh.sharedMesh != null;
            if (visible)
            {
                Mesh original = sourceMesh.sharedMesh;
                original.GetVertices(quad); original.GetColors(sourceColors);
                visible = quad.Count == 4 && sourceColors.Count == 4;
                if (visible)
                {
                    string effect = (string)geometry["effect"];
                    if (lastSprite != name || lastScale != sprite.scale || !lastColor.Equals(sourceColors[0]))
                    {
                        mesh.Clear();
                        if (effect != null)
                        {
                            mesh.SetVertices(quad); mesh.uv = EffectUv; mesh.SetColors(sourceColors);
                            mesh.triangles = original.triangles; mesh.RecalculateBounds();
                        }
                        lastSprite = name; lastScale = sprite.scale; lastColor = sourceColors[0];
                    }
                    effects.layer = source.gameObject.layer;
                    if (effect != null)
                    {
                        if (!Textures.TryGetValue(effect, out var texture))
                        {
                            texture = SteveRig.ReadTexture(effect); texture.filterMode = FilterMode.Bilinear;
                            Textures.Add(effect, texture);
                        }
                        if (!materials.TryGetValue(effect, out var material))
                            materials.Add(effect, material = new Material(source.sharedMaterial));
                        material.CopyPropertiesFromMaterial(source.sharedMaterial); material.mainTexture = texture;
                        effectRenderer.sharedMaterial = material;
                    }
                    effectRenderer.sortingLayerID = source.sortingLayerID;
                    effectRenderer.sortingOrder = source.sortingOrder;
                    source.GetPropertyBlock(properties); effectRenderer.SetPropertyBlock(properties);
                    arm ??= new SteveRig(solidVoid: true);
                    arm.FrameVoidHand(source, Anchor(geometry["armStart"]), Anchor(geometry["armEnd"]), sprite.color.a);
                }
            }
            if (source != null) source.forceRenderingOff = visible;
            if (effects != null) effects.SetActive(visible);
            arm?.Show(visible);
            return visible;
        }
        private Vector3 Point(float x, float y) => quad[0] + (quad[1] - quad[0]) * x + (quad[2] - quad[0]) * y;
        private Vector3 Anchor(JToken value) => sprite.transform.TransformPoint(Point((float)value[0], 1 - (float)value[1]));
        public void Dispose()
        {
            if (source != null) source.forceRenderingOff = false;
            if (effects != null) effects.SetActive(false);
            arm?.Dispose();
            foreach (var material in materials.Values) UnityEngine.Object.Destroy(material);
            materials.Clear();
            UnityEngine.Object.Destroy(mesh); UnityEngine.Object.Destroy(effects);
        }
    }
}
