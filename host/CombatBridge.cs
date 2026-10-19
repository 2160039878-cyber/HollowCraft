using System;
using System.Collections.Generic;
using HollowCraft.Link;
using UnityEngine;
using GlobalEnums;

namespace HollowCraft
{
    internal sealed class CombatBridge
    {
        private readonly Dictionary<HealthManager, uint> ids = new Dictionary<HealthManager, uint>();
        private readonly Dictionary<uint, HealthManager> enemies = new Dictionary<uint, HealthManager>();
        private readonly ActorRecord[] records = new ActorRecord[Proto.MaxActors];
        private readonly RaycastHit2D[] blockers = new RaycastHit2D[128];
        private readonly List<Collider2D> bodyColliders = new List<Collider2D>();
        private readonly EventGate gate;
        private readonly PlayerBridge player;
        private HealthManager[] active = Array.Empty<HealthManager>();
        private uint nextId = 1;
        private float nextScan;
        public int LastExplosionTargets { get; private set; }
        public int ActorCount { get; private set; }
        public object LastPlayerExplosion { get; private set; }
        public event Action<Vector3, float> Exploded;
        public CombatBridge(ulong session, PlayerBridge player) { gate = new EventGate(session); this.player = player; }

        public void Clear()
        {
            ids.Clear(); enemies.Clear(); active = Array.Empty<HealthManager>(); nextScan = 0; ActorCount = 0;
        }

        public void Frame(uint world, uint epoch, HeroController hero)
        {
            if (Time.realtimeSinceStartup >= nextScan)
            {
                active = UnityEngine.Object.FindObjectsByType<HealthManager>(FindObjectsSortMode.None);
                nextScan = Time.realtimeSinceStartup + .25f;
            }
            int count = 0;
            foreach (HealthManager enemy in active)
            {
                if (!IsTarget(enemy) || !TryBodyBounds(enemy, out Bounds bounds)) continue;
                if (count == records.Length) throw new InvalidOperationException("Enemy bridge capacity exceeded");
                if (!ids.TryGetValue(enemy, out uint id)) { id = nextId++; ids[enemy] = id; enemies[id] = enemy; }
                Coords.ToMc(new Vector3(bounds.center.x, bounds.min.y, Coords.Depth), out double x, out double y, out double z);
                records[count++] = new ActorRecord { FormId = id, Flags = Proto.ActorHostile,
                    X = (float)x, Y = (float)y, Z = (float)z, Width = Mathf.Max(.1f, bounds.size.x * Coords.K),
                    Height = Mathf.Max(.1f, bounds.size.y * Coords.K), HealthFrac = 1, Level = 1, Name = enemy.name };
            }
            SharedLink.Instance.WriteActors(records, count); ActorCount = count;
            while (SharedLink.Instance.PopEvent(out McEvent message))
            {
                if (!gate.Accept(message.Session, message.World, message.Epoch, message.EventId, world, epoch)
                    || !DamageRules.Finite(message.A) || !DamageRules.Finite(message.B)
                    || !DamageRules.Finite(message.C) || !DamageRules.Finite(message.D)) continue;
                if (message.Type == Proto.EvShieldResult)
                    player.ResolveShield(message.FormId, message.A, message.B, message.C);
                else if (message.Type == Proto.EvHitActor && enemies.TryGetValue(message.FormId, out HealthManager enemy))
                    Hit(enemy, DamageRules.Enemy(message.A), new Vector2(message.B, message.C), hero.gameObject, 1);
                else if (message.Type == Proto.EvPlayerHurt)
                    HurtHero(hero, DamageRules.Player(message.A), hero.transform.position + Vector3.left);
                else if (message.Type == Proto.EvExplosion && message.D > 0 && message.D <= 32)
                {
                    Vector3 centre = Coords.ToUnity(message.A, message.B, message.C);
                    if (Math.Abs(message.C - Coords.PlaneZ) > message.D * 2) continue;
                    Blast(centre, message.D, hero);
                }
            }
        }

        private bool TryBodyBounds(HealthManager enemy, out Bounds bounds)
        {
            bounds = default;
            bodyColliders.Clear(); enemy.GetComponentsInChildren(false, bodyColliders);
            bool found = false;
            foreach (Collider2D collider in bodyColliders)
            {
                if (!collider.isActiveAndEnabled || collider.gameObject.layer != enemy.gameObject.layer) continue;
                IHitResponder responder = null;
                Transform owner = collider.transform;
                for (int depth = 0; owner != null && depth < 3 && responder == null; depth++, owner = owner.parent)
                    responder = owner.GetComponent<IHitResponder>();
                if (responder as HealthManager != enemy) continue;
                Bounds part = collider.bounds;
                if (part.size.x <= 0 || part.size.y <= 0) continue;
                if (found) bounds.Encapsulate(part); else { bounds = part; found = true; }
            }
            return found;
        }

        private static bool IsTarget(HealthManager enemy)
        {
            // HitTaker selects the first responder; some native bosses carry multiple HealthManagers.
            return enemy != null && enemy.hp > 0 && enemy.gameObject.activeInHierarchy
                && enemy.GetComponent<IHitResponder>() as HealthManager == enemy;
        }

        private float Exposure(Vector3 centre, Bounds bounds)
        {
            // Vanilla's AABB sampling density. Z samples coincide in this extruded side-view plane.
            double dx = 1 / (bounds.size.x * Coords.K * 2 + 1), dy = 1 / (bounds.size.y * Coords.K * 2 + 1);
            double offsetX = (1 - Math.Floor(1 / dx) * dx) / 2;
            int visible = 0, samples = 0, mask = LayerMask.GetMask("Terrain");
            for (double x = 0; x <= 1; x += dx)
            for (double y = 0; y <= 1; y += dy)
            {
                Vector2 point = new Vector2(bounds.min.x + (float)x * bounds.size.x + (float)offsetX / Coords.K,
                    bounds.min.y + (float)y * bounds.size.y);
                int count = Physics2D.LinecastNonAlloc(centre, point, blockers, mask);
                bool blocked = count == blockers.Length;
                for (int i = 0; i < count && !blocked; i++) blocked = blockers[i].collider != null && !blockers[i].collider.isTrigger;
                if (!blocked) visible++;
                samples++;
            }
            return samples > 0 ? visible / (float)samples : 0;
        }

        private void Blast(Vector3 centre, float power, HeroController hero)
        {
            var source = new GameObject("HollowCraft TNT blast");
            source.transform.position = centre;
            LastExplosionTargets = 0;
            try
            {
                foreach (HealthManager enemy in active)
                {
                    if (!IsTarget(enemy) || !TryBodyBounds(enemy, out Bounds bounds)) continue;
                    float distance = Vector2.Distance(new Vector2(bounds.center.x, bounds.min.y), centre) * Coords.K;
                    if (distance > power * 2) continue;
                    float exposure = Exposure(centre, bounds);
                    int damage = DamageRules.Enemy(DamageRules.Explosion(power, distance, exposure));
                    float impact = DamageRules.ExplosionKnockback(power, distance, exposure);
                    if (damage > 0) { Hit(enemy, damage, enemy.transform.position - centre, source, 1.5f * impact); LastExplosionTargets++; }
                }
                Collider2D playerCollider = hero.GetComponent<Collider2D>();
                if (playerCollider != null)
                {
                    Bounds bounds = playerCollider.bounds;
                    float distance = Vector2.Distance(new Vector2(bounds.center.x, bounds.min.y), centre) * Coords.K;
                    if (distance <= power * 2)
                    {
                        float exposure = Exposure(centre, bounds);
                        float raw = DamageRules.Explosion(power, distance, exposure);
                        float impact = DamageRules.ExplosionKnockback(power, distance, exposure);
                        int masks = DamageRules.Player(raw), before = PlayerData.instance.health;
                        bool immune = hero.cState.invulnerable;
                        float recoilSpeed = hero.RECOIL_VELOCITY;
                        // StartRecoil captures this speed before its first yield; restore it for every other native hit.
                        try { hero.RECOIL_VELOCITY = recoilSpeed * impact; HurtHero(hero, masks, centre, source); }
                        finally { hero.RECOIL_VELOCITY = recoilSpeed; }
                        LastPlayerExplosion = new { distance, exposure, raw, masks, impact, recoilSpeed,
                            before, after = PlayerData.instance.health, immune };
                        Log.Info("Player explosion: " + Newtonsoft.Json.JsonConvert.SerializeObject(LastPlayerExplosion));
                    }
                }
                Exploded?.Invoke(centre, power);
                Log.Info($"TNT explosion: power {power}, enemy targets {LastExplosionTargets}");
            }
            finally { UnityEngine.Object.Destroy(source, 1); }
        }

        private void Hit(HealthManager enemy, int damage, Vector2 direction, GameObject source, float force)
        {
            if (!IsTarget(enemy) || damage <= 0 || !TryBodyBounds(enemy, out _)) return;
            enemy.Hit(new HitInstance { Source = source, AttackType = AttackTypes.Generic, DamageDealt = damage,
                Direction = Mathf.Repeat(Mathf.Atan2(direction.y, direction.x) * Mathf.Rad2Deg, 360),
                IgnoreInvulnerable = false, Multiplier = 1, MagnitudeMultiplier = force });
        }

        private static void HurtHero(HeroController hero, int damage, Vector3 origin, GameObject source = null)
        {
            if (damage <= 0 || hero == null || hero.cState.dead) return;
            hero.TakeDamage(source, origin.x < hero.transform.position.x ? CollisionSide.left : CollisionSide.right, damage, 1);
        }
    }
}
