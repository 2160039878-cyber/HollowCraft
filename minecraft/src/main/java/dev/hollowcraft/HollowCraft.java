package dev.hollowcraft;

import dev.hollowcraft.combat.HostCombat;
import dev.hollowcraft.link.HostLink;
import net.fabricmc.api.ModInitializer;
import net.fabricmc.fabric.api.event.lifecycle.v1.ServerLifecycleEvents;
import net.fabricmc.fabric.api.networking.v1.ServerPlayConnectionEvents;
import net.minecraft.server.MinecraftServer;
import net.minecraft.server.level.ServerPlayer;
import net.minecraft.world.item.Item;
import net.minecraft.world.item.ItemStack;
import net.minecraft.world.item.Items;
import net.minecraft.world.level.gamerules.GameRules;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

public final class HollowCraft implements ModInitializer {
    public static final String MOD_ID = "hollowcraft";
    public static final String WORLD_NAME = "HollowCraft";
    public static boolean managedWorld(String name) { return WORLD_NAME.equals(name) || name.matches("HollowCraft-[1-4]-[a-f0-9]{32}"); }
    public static final Logger LOG = LoggerFactory.getLogger(MOD_ID);
    private static final String KIT = "hollowcraft_sandbox_v1";
    @Override public void onInitialize() {
        HostCombat.init();
        dev.hollowcraft.net.RepoNet.init();
        dev.hollowcraft.world.HostDig.init();
        ServerLifecycleEvents.SERVER_STARTED.register(HollowCraft::configureServer);
        ServerPlayConnectionEvents.JOIN.register((handler, sender, server) -> {
            ServerPlayer player = handler.getPlayer();
            if (player.getY() < player.level().getMinY() + 16) {
                player.teleportTo(player.level(), 0, 0, .5, java.util.Set.of(), -90, 0, false);
                player.resetFallDistance();
            }
            if (!player.entityTags().contains(KIT)) {
                refill(player);
                player.addTag(KIT);
            }
        });
        net.fabricmc.fabric.api.event.lifecycle.v1.ServerTickEvents.END_SERVER_TICK.register(server -> {
            RedstoneProbe.tick(server);
            GameplayProbe.tick(server);
            if (!HostLink.active()) return;
            HostLink.HostState state = new HostLink.HostState();
            if (!HostLink.readSkyState(state)) return;
            for (ServerPlayer player : server.getPlayerList().getPlayers()) {
                var maxHealth = player.getAttribute(net.minecraft.world.entity.ai.attributes.Attributes.MAX_HEALTH);
                if (maxHealth != null) maxHealth.setBaseValue(Math.clamp(state.maxHealth * 4.0, 4.0, 400.0));
                player.setHealth(Math.clamp(state.health * 4.0f, 1.0f, player.getMaxHealth()));
                player.getFoodData().setFoodLevel(20);
                player.getFoodData().setSaturation(20);
                player.setNoGravity(state.nativeControl());
            }
        });
        net.fabricmc.fabric.api.command.v2.CommandRegistrationCallback.EVENT.register((dispatcher, context, environment) ->
            dispatcher.register(net.minecraft.commands.Commands.literal("hollowcraft_refill")
                .executes(command -> { refill(command.getSource().getPlayerOrException()); return 1; })));
    }
    private static void configureServer(MinecraftServer server) {
        dev.hollowcraft.world.RoomVersions.load(server);
        GameRules rules = server.getGameRules();
        rules.set(GameRules.ADVANCE_TIME, false, server);
        rules.set(GameRules.ADVANCE_WEATHER, false, server);
        rules.set(GameRules.SPAWN_MOBS, false, server);
        rules.set(GameRules.SPAWN_MONSTERS, false, server);
        rules.set(GameRules.SPAWN_PHANTOMS, false, server);
        rules.set(GameRules.SPAWN_PATROLS, false, server);
        rules.set(GameRules.SPAWN_WANDERING_TRADERS, false, server);
        rules.set(GameRules.PLAYER_MOVEMENT_CHECK, false, server);
        rules.set(GameRules.KEEP_INVENTORY, true, server);
        rules.set(GameRules.NATURAL_HEALTH_REGENERATION, false, server);
        rules.set(GameRules.SHOW_ADVANCEMENT_MESSAGES, false, server);
        server.getCommands().performPrefixedCommand(server.createCommandSourceStack().withSuppressedOutput(), "time set noon");
    }
    public static void refill(ServerPlayer player) {
        if (player.getOffhandItem().isEmpty())
            player.setItemInHand(net.minecraft.world.InteractionHand.OFF_HAND, new ItemStack(Items.SHIELD));
        Item[] items = {Items.DIAMOND_SWORD, Items.DIAMOND_PICKAXE, Items.STONE, Items.TNT, Items.REDSTONE,
            Items.LEVER, Items.REPEATER, Items.OAK_BUTTON, Items.BOW, Items.ARROW, Items.IRON_SWORD,
            Items.STONE_SWORD, Items.OAK_PLANKS, Items.GLASS, Items.REDSTONE_TORCH, Items.REDSTONE_BLOCK,
            Items.PISTON, Items.STICKY_PISTON, Items.OBSERVER, Items.CROSSBOW};
        for (Item item : items) {
            int missing = Math.min(64, item.getDefaultMaxStackSize()) - player.getInventory().countItem(item);
            if (missing > 0) player.getInventory().add(new ItemStack(item, missing));
        }
        player.containerMenu.broadcastChanges();
    }
}
