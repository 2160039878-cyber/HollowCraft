package dev.hollowcraft.combat;

import dev.hollowcraft.HollowCraft;
import dev.hollowcraft.link.HostLink;
import dev.hollowcraft.link.Proto;
import net.minecraft.core.component.DataComponents;
import net.minecraft.core.registries.Registries;
import net.minecraft.server.level.ServerPlayer;
import net.minecraft.world.damagesource.DamageSource;
import net.minecraft.world.damagesource.DamageTypes;
import net.minecraft.world.item.Items;

/** Minecraft owns shield delay, angle, durability and sound; HK alone owns health. */
public final class ShieldBridge {
    private ShieldBridge() { }
    public static void block(ServerPlayer player, HostLink.Scope scope, int code, float amount, int request) {
        float blocked = 0;
        var stack = player.getUseItem();
        int before = stack.is(Items.SHIELD) ? stack.getDamageValue() : -1;
        int useTicks = player.getTicksUsingItem();
        if (player.isAlive() && stack.is(Items.SHIELD) && player.isBlocking()) {
            var component = stack.get(DataComponents.BLOCKS_ATTACKS);
            double angle = Math.toRadians((code & 32767) / 50.0);
            // Rotate the side-view XY attack plane into vanilla's horizontal shield cone.
            var position = player.position().add(Math.cos(angle), 0, Math.sin(angle));
            var type = (code & 32768) != 0 ? DamageTypes.EXPLOSION : DamageTypes.MOB_ATTACK;
            var source = new DamageSource(player.registryAccess().lookupOrThrow(Registries.DAMAGE_TYPE).getOrThrow(type), position);
            blocked = player.applyItemBlocking(player.level(), source, amount);
            if (blocked > 0 && component != null) component.onBlocked(player.level(), player);
            player.containerMenu.broadcastChanges();
        }
        int after = stack.isEmpty() ? -1 : stack.getDamageValue();
        HostLink.pushEvent(scope, Proto.EV_SHIELD_RESULT, request, blocked, before, after, useTicks, 0, 0);
        HollowCraft.LOG.info("HollowCraft shield: request={} damage={} blocked={} wear={}->{} useTicks={}", request, amount, blocked, before, after, useTicks);
    }
}
