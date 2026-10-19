using System;
using System.IO;
using System.Linq;
using System.Collections.Generic;
using HollowCraft.World;
using Newtonsoft.Json;
using UnityEngine;

namespace HollowCraft
{
    // Read-only geometry evidence, invoked only by the explicitly enabled development probe.
    internal static class TerrainProbe
    {
        private static string PathOf(Transform node) => node.parent == null ? node.name : PathOf(node.parent)+"/"+node.name;
        private static float[] Point(Vector3 point) => new[] { point.x,point.y,point.z };
        private static object Box(Bounds bounds) => new {min=Point(bounds.min),max=Point(bounds.max)};
        private static bool Near(Bounds bounds,Vector2? point) => point.HasValue
            && point.Value.x>=bounds.min.x-2 && point.Value.x<=bounds.max.x+2
            && point.Value.y>=bounds.min.y-2 && point.Value.y<=bounds.max.y+2;

        public static void Write(string directory,Vector2? point)
        {
            var scene=UnityEngine.SceneManagement.SceneManager.GetActiveScene();
            var colliders=UnityEngine.Object.FindObjectsByType<Collider2D>(FindObjectsInactive.Include,FindObjectsSortMode.None)
                .Where(c=>c.gameObject.scene==scene).Select(c=>new {
                    id=c.GetInstanceID(),path=PathOf(c.transform),type=c.GetType().Name,c.enabled,c.isTrigger,
                    active=c.gameObject.activeInHierarchy,c.gameObject.layer,bounds=Box(c.bounds),
                    diggable=TerrainCutter.Diggable(c),cut=c.GetComponent<HollowCraftTerrainPiece>()!=null,
                    original=c.GetComponent<HollowCraftTerrainPiece>()?.Original?.GetInstanceID(),
                    edgePoints=c is EdgeCollider2D edge ? edge.points.Select(v=>Point(edge.transform.TransformPoint(v+edge.offset))).ToArray() : null,
                    contains=point.HasValue && c.enabled && c.OverlapPoint(point.Value)
                }).ToArray();
            var renderers=UnityEngine.Object.FindObjectsByType<Renderer>(FindObjectsInactive.Include,FindObjectsSortMode.None)
                .Where(r=>r.gameObject.scene==scene && (r is SpriteRenderer || r.GetComponent<MeshFilter>()!=null)).Select(r=>{
                    Mesh mesh=r.GetComponent<MeshFilter>()?.sharedMesh;
                    Vector3[] vertices=Array.Empty<Vector3>();int[] triangles=Array.Empty<int>();Vector2[] uv=Array.Empty<Vector2>();
                    if(Near(r.bounds,point))
                    {
                        if(r is SpriteRenderer sprite && sprite.sprite!=null)
                        {
                            vertices=sprite.sprite.vertices.Select(v=>r.transform.TransformPoint(new Vector3(
                                v.x*(sprite.flipX ? -1 : 1),v.y*(sprite.flipY ? -1 : 1),0))).ToArray();
                            triangles=sprite.sprite.triangles.Select(v=>(int)v).ToArray();uv=sprite.sprite.uv;
                        }
                        else if(mesh!=null && mesh.isReadable)
                        { vertices=mesh.vertices.Select(v=>r.transform.TransformPoint(v)).ToArray();triangles=mesh.triangles;uv=mesh.uv; }
                    }
                    return new {id=r.GetInstanceID(),path=PathOf(r.transform),type=r.GetType().Name,r.enabled,
                        active=r.gameObject.activeInHierarchy,r.forceRenderingOff,r.gameObject.layer,bounds=Box(r.bounds),
                        materials=r.sharedMaterials.Select(m=>m==null ? null : new {m.name,shader=m.shader?.name,texture=m.mainTexture?.name}),
                        vertices=vertices.Select(Point),triangles,uv=uv.Select(v=>new[]{v.x,v.y})};
                }).ToArray();
            var directions=new[]{Vector2.left,Vector2.right,Vector2.up,Vector2.down};
            var rays=point.HasValue ? directions.Select(direction=>new {
                direction=new[]{direction.x,direction.y},hits=Physics2D.RaycastAll(point.Value,direction,2,LayerMask.GetMask("Terrain"))
                    .Where(h=>h.collider!=null && !h.collider.isTrigger).Select(h=>new {h.distance,point=new[]{h.point.x,h.point.y},path=PathOf(h.collider.transform)})
            }).ToArray() : null;
            var cutter=TerrainCutter.Instance;
            var removed=new List<(int x,int y,int z)>();
            if(point.HasValue)
            {
                var low=Coords.ToMcF(new Vector3(point.Value.x-4,point.Value.y-4,Coords.Depth));
                var high=Coords.ToMcF(new Vector3(point.Value.x+4,point.Value.y+4,Coords.Depth));
                DugBlocks.Collect(low.x,low.y,(float)Coords.PlaneZ,high.x,high.y,(float)Coords.PlaneZ,removed);
            }
            var output=new {scene=scene.name,point=point.HasValue ? new[]{point.Value.x,point.Value.y} : null,
                Coords.K,Coords.OffsetX,Coords.PlaneZ,cutter.CutCount,cutter.CutColliderCount,cutter.Pending,
                Physics2D.queriesStartInColliders,removed=removed.Select(c=>new[]{c.x,c.y,c.z}),colliders,renderers,rays};
            CheckpointFiles.Write(System.IO.Path.Combine(directory,"hollowcraft-terrain-inventory.json"),
                System.Text.Encoding.UTF8.GetBytes(JsonConvert.SerializeObject(output)));
        }
    }
}
