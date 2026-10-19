package dev.hollowcraft.client;

import dev.hollowcraft.combat.HostCombat;
import dev.hollowcraft.link.HostLink;
import dev.hollowcraft.world.HostCollision;
import net.fabricmc.api.ClientModInitializer;
import net.fabricmc.fabric.api.client.event.lifecycle.v1.ClientTickEvents;
import net.fabricmc.fabric.api.client.rendering.v1.EntityRendererRegistry;
import net.minecraft.client.renderer.entity.NoopRenderer;
import net.minecraft.world.entity.player.Player;

public final class HollowCraftClient implements ClientModInitializer {
    @Override
    public void onInitializeClient() {
        HostLink.announceRunning();
        DestructionToggle.register();
        ClientTickEvents.END_CLIENT_TICK.register(HostClient::clientTick);
        EntityRendererRegistry.register(HostCombat.HOST_ACTOR, NoopRenderer::new);
        HostCollision.setSmoothCollider(entity -> entity instanceof Player && HostClient.linked());
    }
}
