using System;
using System.Collections.Generic;
using System.IO;
using System.Text;
using HollowCraft.Link;
using HollowCraft.World;
using Newtonsoft.Json;
using UnityEngine;

namespace HollowCraft
{
    internal sealed class RecoveryTools
    {
        private sealed class Request { public string id, session; public uint world, epoch; }
        private sealed class Response { public string id, status, error; public uint world, epoch; public int revision; }
        private readonly Checkpoints checkpoints;
        private readonly Action<Vector2> teleport;
        private readonly List<Vector2> safe = new List<Vector2>();
        private HeroController hero;
        private HostState host;
        private Request request;
        private uint trackedWorld;
        private int phase, stableFrames;
        private bool open, ready;
        private float nextSample, started;
        private string status = "F8 打开/关闭恢复工具";
        public bool BlocksInput => open || phase != 0;
        public bool Busy => phase != 0;
        public string Status => status;
        public int SafePoints => safe.Count;
        public object LastSafetyCheck { get; private set; }
        public readonly List<object> CandidateChecks = new List<object>();
        private string Bridge(string name) => Path.Combine(Application.persistentDataPath,"hollowcraft-checkpoints","bridge",name+".json");

        public RecoveryTools(Checkpoints checkpoints, Action<Vector2> teleport) { this.checkpoints=checkpoints; this.teleport=teleport; }
        private bool CanOperate => ready && hero!=null && hero.acceptingInput && !hero.cState.dead && !hero.cState.transitioning
            && !hero.cState.attacking && !hero.cState.dashing && !hero.cState.recoiling && !hero.cState.focusing;
        public void Frame(HeroController current, HostState state, bool linkedReady, bool peerScreen)
        {
            try { Update(current,state,linkedReady,peerScreen); }
            catch(Exception error) { phase=0; open=true; status="恢复失败，检查点保留："+error.Message; Log.Error("Recovery: "+error); }
        }
        private void Update(HeroController current, HostState state, bool linkedReady, bool peerScreen)
        {
            hero=current; host=state; ready=linkedReady;
            if (trackedWorld!=host.WorldId)
            {
                trackedWorld=host.WorldId; safe.Clear();
                if (Busy) { phase=0; status="房间已切换，恢复操作已取消；检查点保留。"; }
                open=false;
            }
            if (hero==null) { open=false; return; }
            if (Input.GetKeyDown(KeyCode.F8) && !Busy && !peerScreen && !GameManager.instance.isPaused && (open || CanOperate))
                open=!open;
            if (open && Input.GetKeyDown(KeyCode.Escape)) Close();
            float now=Time.realtimeSinceStartup;
            if (CanOperate && !BlocksInput && hero.cState.onGround && now>=nextSample)
            {
                nextSample=now+.5f;
                Vector2 position=hero.GetComponent<Rigidbody2D>().position;
                if (Safe(position) && (safe.Count==0 || Vector2.Distance(safe[safe.Count-1],position)>.75f))
                { if(safe.Count==32) safe.RemoveAt(0); safe.Add(position); }
            }
            if (Busy && now-started>120) { phase=0; status="恢复超时；最近成功检查点保留。"; }
            if (phase==2)
            {
                request=new Request { id=Guid.NewGuid().ToString("N"),session=SharedLink.Instance.Session.ToString("x16"),world=host.WorldId,epoch=host.CollisionEpoch };
                CheckpointFiles.Write(Bridge("restore-room"),Encoding.UTF8.GetBytes(JsonConvert.SerializeObject(request)));
                phase=3; status="正在还原本房间地形…";
            }
            if (phase==3)
            {
                if (request.world!=host.WorldId || request.epoch!=host.CollisionEpoch) { phase=0; status="连接或场景已改变；恢复已中止。"; return; }
                string path=Bridge("restore-room-status");
                string text=CheckpointFiles.ReadControl(path,true);
                if(text==null) return;
                var result=JsonConvert.DeserializeObject<Response>(text);
                if (result?.id!=request.id || result.world!=request.world || result.epoch!=request.epoch) return;
                if (result.status=="error") { phase=0; status="恢复失败："+result.error; return; }
                if (result.status!="ready") return;
                TerrainCutter.Instance.Clear(); DugBlocks.Clear(); Physics2D.SyncTransforms();
                if (!FindSafe(out Vector2 point)) { teleport(hero.transform.position); phase=0; status="地形已还原，但未找到安全落脚点。恢复前检查点保留。"; return; }
                teleport(point); phase=4; stableFrames=0; status="正在同步房间碰撞…";
            }
            if (phase==4 && ready && TerrainCutter.Instance.Pending==0 && TerrainCutter.Instance.CutCount==0)
            {
                if (++stableFrames<3) return;
                phase=5; status="正在保存恢复后的房间…";
                uint world=host.WorldId;
                GameManager.instance.SaveGame(saved => { if(phase!=5 || host.WorldId!=world) return; phase=0; status=saved ? "当前房间原生地形已还原；建筑和背包保留。" : "地形已还原，保存失败；恢复前检查点保留。"; });
            }
        }
        public void RestoreRoom()
        {
            if (Busy || !CanOperate || checkpoints.Saving) { status="请等待当前动作结束和连接恢复。"; return; }
            open=true; phase=1; started=Time.realtimeSinceStartup; status="正在保存恢复前检查点…";
            uint world=host.WorldId;
            GameManager.instance.SaveGame(saved => {
                if (phase!=1) return;
                if (saved && host.WorldId==world) phase=2;
                else { phase=0; status="检查点未保存，地形保持原状。"; }
            });
        }
        public void ReturnSafe()
        {
            if (Busy || !CanOperate) { status="请等待当前动作结束和连接恢复。"; return; }
            if (!FindSafe(out Vector2 point,true)) { status="未找到更早的安全位置，可先还原当前房间地形。"; return; }
            teleport(point); status="已返回最近有效安全位置。";
        }
        public void Close() { if(!Busy) open=false; }
        private bool FindSafe(out Vector2 point,bool earlier=false)
        {
            CandidateChecks.Clear();
            for (int i=safe.Count-1;i>=0;i--)
            {
                if(earlier && Vector2.Distance(safe[i],hero.GetComponent<Rigidbody2D>().position)<.5f) continue;
                bool valid=Safe(safe[i]); CandidateChecks.Add(LastSafetyCheck); if(valid) { point=safe[i]; return true; }
            }
            Vector3 marker=PlayerData.instance.GetVector3("hazardRespawnLocation");
            if(DamageRules.Finite(marker.x) && DamageRules.Finite(marker.y))
            {
                var hit=Physics2D.Raycast(marker,Vector2.down,100,LayerMask.GetMask("Terrain"));
                if(hit.collider!=null && hit.normal.y>.75f)
                {
                    float offset=hero.GetComponent<Rigidbody2D>().position.y-hero.GetComponent<Collider2D>().bounds.min.y;
                    point=hit.point+Vector2.up*(offset+.02f);
                    bool valid=Safe(point); CandidateChecks.Add(LastSafetyCheck); if(valid) return true;
                }
            }
            point=default; return false;
        }
        private bool Safe(Vector2 position)
        {
            Collider2D own=hero.GetComponent<Collider2D>();
            // Collider bounds use the physics pose; the visible transform can lag while Rigidbody2D interpolation is active.
            Vector2 center=position+(Vector2)own.bounds.center-hero.GetComponent<Rigidbody2D>().position;
            Vector2 size=Vector2.Scale(own.bounds.size,new Vector2(.94f,.94f));
            foreach(var collider in Physics2D.OverlapBoxAll(center,size,0))
            {
                if(collider==own || collider.GetComponentInParent<HeroController>()!=null) continue;
                if(collider.GetComponentInParent<DamageHero>()!=null || (!collider.isTrigger && collider.gameObject.layer==LayerMask.NameToLayer("Terrain")))
                { LastSafetyCheck=new { x=position.x,y=position.y,reason="overlap",collider=collider.name,layer=collider.gameObject.layer,trigger=collider.isTrigger }; return false; }
            }
            var ground=Physics2D.Raycast(new Vector2(center.x,center.y-own.bounds.extents.y+.04f),Vector2.down,.16f,LayerMask.GetMask("Terrain"));
            bool valid=ground.collider!=null && ground.normal.y>.75f && !ground.collider.isTrigger && ground.collider.GetComponentInParent<DamageHero>()==null
                && (ground.collider.GetComponentInParent<HollowCraftGeometry>()==null || ground.collider.GetComponent<HollowCraftTerrainPiece>()!=null);
            LastSafetyCheck=new { x=position.x,y=position.y,reason=valid?"safe":"support",collider=ground.collider?.name,ny=ground.normal.y,trigger=ground.collider!=null && ground.collider.isTrigger,feet=center.y-own.bounds.extents.y };
            return valid;
        }
        public void OnGUI()
        {
            if (!open || hero==null) return;
            float width=Mathf.Min(460,Screen.width-32),left=(Screen.width-width)/2;
            GUI.Box(new Rect(left,90,width,300),"HollowCraft 恢复工具");
            GUI.enabled=!Busy;
            if(GUI.Button(new Rect(left+18,128,width-36,38),"返回最近安全位置")) ReturnSafe();
            if(GUI.Button(new Rect(left+18,174,width-36,38),"还原当前房间地形（保留建筑与背包）")) RestoreRoom();
            if(GUI.Button(new Rect(left+18,220,width-36,38),"补充物资（F7）")) SharedLink.Instance.PushInput(Proto.InRefill,0,0);
            if(GUI.Button(new Rect(left+18,332,width-36,38),"关闭（F8）")) Close();
            GUI.enabled=true;
            GUI.Label(new Rect(left+18,268,width-36,56),status);
        }
    }
}
