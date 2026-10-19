using System;

namespace HollowCraft
{
    internal enum MovementOwner { Minecraft, Knight }

    internal sealed class ControlState
    {
        public MovementOwner Owner { get; private set; } = MovementOwner.Knight;
        public uint Generation { get; private set; } = 1;
        public bool AirJumpUsed { get; private set; }

        public bool RequestOwner(bool holdingSword, bool actionLocked)
        {
            MovementOwner requested = holdingSword ? MovementOwner.Knight : MovementOwner.Minecraft;
            if (actionLocked || requested == Owner) return false;
            Owner = requested;
            Generation++;
            return true;
        }

        public bool TryAirJump(bool abilityUnlocked, bool grounded)
        {
            if (!abilityUnlocked || grounded || AirJumpUsed) return false;
            AirJumpUsed = true;
            return true;
        }

        public void Land() => AirJumpUsed = false;
        public void ConsumeAirJump() => AirJumpUsed = true;
    }

    internal static class DamageRules
    {
        public static bool Finite(double value) => !double.IsNaN(value) && !double.IsInfinity(value);

        private static double BlastImpact(float power, float distance, float exposure)
        {
            if (!Finite(power) || !Finite(distance) || !Finite(exposure) || power <= 0 || power > 32 || distance < 0 || exposure < 0)
                return -1;
            float reach = power * 2;
            if (distance > reach) return -1;
            return (1 - (double)distance / reach) * Math.Min(1, exposure);
        }

        public static float Explosion(float power, float distance, float exposure)
        {
            double impact = BlastImpact(power, distance, exposure);
            // Minecraft 26.3 keeps fractional damage and the in-range +1 term even with zero exposure.
            return impact < 0 ? 0 : (float)((impact * impact + impact) * 0.5 * 7 * (power * 2) + 1);
        }

        public static float ExplosionKnockback(float power, float distance, float exposure)
            => (float)Math.Max(0, BlastImpact(power, distance, exposure));

        public static int Enemy(float minecraftDamage)
            => Finite(minecraftDamage) && minecraftDamage > 0 ? (int)Math.Min(100000, Math.Round(minecraftDamage * 3)) : 0;

        public static int Player(float minecraftDamage)
            => Finite(minecraftDamage) && minecraftDamage > 0 ? (int)Math.Min(1000, Math.Ceiling(minecraftDamage / 4)) : 0;
    }

    internal sealed class EventGate
    {
        private readonly ulong session;
        private ulong lastId;
        private uint currentWorld, currentEpoch;
        public EventGate(ulong sessionId) => session = sessionId;

        public bool Accept(ulong eventSession, uint eventWorld, uint eventEpoch, ulong eventId, uint world, uint epoch)
        {
            if (eventSession != session || eventWorld != world || eventEpoch != epoch || eventId == 0)
                return false;
            if (currentWorld != world || currentEpoch != epoch)
            {
                currentWorld = world; currentEpoch = epoch; lastId = 0;
            }
            if (eventId <= lastId) return false;
            lastId = eventId;
            return true;
        }
    }
}
