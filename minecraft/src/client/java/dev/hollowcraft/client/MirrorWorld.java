package dev.hollowcraft.client;

import dev.hollowcraft.HollowCraft;
import net.minecraft.client.Minecraft;
import net.minecraft.client.gui.screens.TitleScreen;
import net.minecraft.core.registries.Registries;
import net.minecraft.resources.Identifier;
import net.minecraft.resources.ResourceKey;
import net.minecraft.world.Difficulty;
import net.minecraft.world.level.GameType;
import net.minecraft.world.level.LevelSettings;
import net.minecraft.world.level.WorldDataConfiguration;
import net.minecraft.world.level.levelgen.WorldOptions;
import net.minecraft.world.level.levelgen.presets.WorldPreset;

/** The bridge only creates or opens its own local world. */
public final class MirrorWorld {
    private static final ResourceKey<WorldPreset> PRESET = ResourceKey.create(Registries.WORLD_PRESET,
        Identifier.fromNamespaceAndPath(HollowCraft.MOD_ID, "mirror"));
    private MirrorWorld() { }

    public static boolean openWhenReady(Minecraft minecraft, String worldName) {
        if (minecraft.level != null || minecraft.gui.overlay() != null) return false;
        if (!(minecraft.gui.screen() instanceof TitleScreen)) {
            if (minecraft.gui.screen() == null || minecraft.gui.screen().getClass().getName().contains("Onboarding"))
                minecraft.gui.setScreen(new TitleScreen());
            return false;
        }
        TitleScreen title = (TitleScreen)minecraft.gui.screen();
        if (minecraft.getLevelSource().levelExists(worldName)) {
            minecraft.createWorldOpenFlows().openWorld(worldName, () -> minecraft.gui.setScreen(title));
            return true;
        }
        LevelSettings settings = new LevelSettings(worldName, GameType.SURVIVAL,
            new LevelSettings.DifficultySettings(Difficulty.NORMAL, false, false), true, WorldDataConfiguration.DEFAULT);
        minecraft.createWorldOpenFlows().createFreshLevel(worldName, settings,
            new WorldOptions(0L, false, false),
            registries -> registries.lookupOrThrow(Registries.WORLD_PRESET).getOrThrow(PRESET).value().createWorldDimensions(), title);
        return true;
    }
}
