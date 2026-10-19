package dev.hollowcraft.client;

import static dev.hollowcraft.link.Proto.DIG_STONE;

import dev.hollowcraft.client.render.WorldExporter;
import dev.hollowcraft.net.RepoNet;
import dev.hollowcraft.world.HostClip;
import dev.hollowcraft.world.HostCollision;
import dev.hollowcraft.world.HostDig;
import dev.hollowcraft.world.HostRay;
import it.unimi.dsi.fastutil.longs.Long2ObjectOpenHashMap;
import java.util.ArrayList;
import java.util.List;
import net.fabricmc.fabric.api.client.networking.v1.ClientPlayNetworking;
import net.minecraft.client.particle.TerrainParticle;
import net.minecraft.client.resources.sounds.SimpleSoundInstance;
import net.minecraft.client.resources.sounds.SoundInstance;
import net.minecraft.sounds.SoundSource;
import net.minecraft.client.Minecraft;
import net.minecraft.client.multiplayer.ClientLevel;
import net.minecraft.core.BlockPos;
import net.minecraft.world.level.ChunkPos;
import net.minecraft.world.level.GameType;
import net.minecraft.world.level.block.state.BlockState;
import net.minecraft.world.level.chunk.LevelChunk;
import net.minecraft.world.level.chunk.status.ChunkStatus;
import org.jspecify.annotations.Nullable;

/**
 * The digging player's side of {@link HostDig}: hitting REPO's geometry asks the server to open that
 * cell, and the dug cells of loaded chunks go to Hollow Knight (WorldExporter).
 */
public final class HostDigClient {
	private HostDigClient() {
	}


	// Mining a REPO surface: which cell, how far along (0..1), on which tick last.
	private static @Nullable BlockPos mining;
	private static float progress;
	private static int miningTick;
	private static int hits;
	private static int ticks;
	private static final Long2ObjectOpenHashMap<HostDig.DugColumn> SEEN = new Long2ObjectOpenHashMap<>();
	private static final HostDig.DugColumn NONE = new HostDig.DugColumn(List.of());
	private static int seenWorld = Integer.MIN_VALUE;
	private static int seenRevision = -1;
	private static int pollTicks;

	/** The REPO world the player is in (worldspace or interior cell). */
	public static int world() {
		return HostClient.sky().worldId;
	}

	/**
	 * The player attacked (clicked or held) REPO geometry under the crosshair: mining it, as long
	 * as mining the block it's made of would take. Returns true if it's being mined.
	 */
	public static boolean attack(Minecraft minecraft) {
		if (!(minecraft.hitResult instanceof HostClip.HostHitResult result) || minecraft.level == null || minecraft.player == null || minecraft.gameMode == null) {
			return false;
		}
		GameType mode = minecraft.gameMode.getPlayerMode();
		if (mode == GameType.ADVENTURE || mode == GameType.SPECTATOR || (!HostDig.destruction && minecraft.hasSingleplayerServer())) {
			return false; // (a guest asks anyway: the host's setting decides)
		}
		HostRay.Hit hit = result.hit;
		if (hit.tri() == null || !hit.tri().diggable) {
			return false; // a building, or something else that stays
		}
		int[] cell = HostRay.surfaceCell(hit);
		BlockPos pos = new BlockPos(cell[0], cell[1], cell[2]);
		BlockState here = minecraft.level.getBlockState(pos);
		if (!here.isAir() && !here.canBeReplaced()) {
			return false;
		}
		if (HostDig.isDug(minecraft.level, world(), pos)) {
			return false;
		}
		// Once a tick (a click and a held button can both land in the same one).
		if (pos.equals(mining) && miningTick == ticks) {
			return true;
		}
		if (!pos.equals(mining) || ticks - miningTick > 2) {
			mining = pos;
			progress = 0.0F;
			hits = 0;
		}
		miningTick = ticks;
		int material = hit.tri().material == 0 ? DIG_STONE : hit.tri().material;
		BlockState state = HostDig.materialState(material);
		progress += minecraft.player.getAbilities().instabuild ? 1.0F : state.getDestroyProgress(minecraft.player, minecraft.level, pos);
		if (hits++ % 4 == 0) {
			var sound = state.getSoundType();
			minecraft.getSoundManager().play(new SimpleSoundInstance(
				sound.getHitSound(), SoundSource.BLOCKS, (sound.getVolume() + 1.0F) / 8.0F, sound.getPitch() * 0.5F, SoundInstance.createUnseededRandom(), pos
			));
			minecraft.particleEngine.add(new TerrainParticle(minecraft.level, hit.x() + hit.nx() * 0.05, hit.y() + hit.ny() * 0.05, hit.z() + hit.nz() * 0.05, 0.0, 0.0, 0.0, state, pos)
				.setPower(0.2F).scale(0.6F));
		}
		if (progress >= 1.0F) {
			ClientPlayNetworking.send(new RepoNet.DigOpen(world(), HostClient.sky().collisionEpoch, HostClient.sky().session, pos, material));
			mining = null;
			progress = 0.0F;
		}
		return true;
	}

	public static void tick(Minecraft minecraft) {
		ticks++;
		ClientLevel level = minecraft.level;
		if (level == null || minecraft.player == null) {
			SEEN.clear();
			return;
		}
		int world = world();
		if (++pollTicks % 5 == 0) {
			pollDug(minecraft, level);
		}
		// REPO's geometry around dug cells arrived or changed: their walls are drawn again.
		HostCollision.takeChangedRegions(key -> {
			int rx = BlockPos.getX(key), ry = BlockPos.getY(key), rz = BlockPos.getZ(key);
			for (int sx = (rx - 1) >> 4; sx <= (rx + 8) >> 4; sx++) {
				for (int sz = (rz - 1) >> 4; sz <= (rz + 8) >> 4; sz++) {
					LevelChunk chunk = level.getChunkSource().getChunk(sx, sz, ChunkStatus.FULL, false);
					if (chunk == null) {
						continue;
					}
					for (int sy = (ry - 1) >> 4; sy <= (ry + 8) >> 4; sy++) {
						if (dugBits(chunk, sy) != null) {
							WorldExporter.markDirty(sx, sy, sz);
						}
					}
				}
			}
		});
	}

	/** Dug cells of this section in the current REPO world, or null. */
	public static long @Nullable [] dugBits(LevelChunk chunk, int sectionY) {
		HostDig.DugColumn column = chunk.getAttached(HostDig.DUG);
		return column == null ? null : column.bits(world(), sectionY);
	}

	/** REPO needs every dug cell again (it cleared them). */
	public static void resendAll() {
		SEEN.clear();
	}

	// Chunks whose dug cells changed (or the player changed REPO world): their sections go to REPO.
	private static void pollDug(Minecraft minecraft, ClientLevel level) {
		int world = world();
		int revision=dev.hollowcraft.world.RoomVersions.current(world);
		boolean worldChanged = world != seenWorld || revision != seenRevision;
		seenWorld = world;
		seenRevision = revision;
		int radius = minecraft.options.getEffectiveRenderDistance() + 1;
		int pcx = minecraft.player.getBlockX() >> 4, pcz = minecraft.player.getBlockZ() >> 4;
		for (int cx = pcx - radius; cx <= pcx + radius; cx++) {
			for (int cz = pcz - radius; cz <= pcz + radius; cz++) {
				long key = ChunkPos.pack(cx, cz);
				LevelChunk chunk = level.getChunkSource().getChunk(cx, cz, ChunkStatus.FULL, false);
				if (chunk == null) {
					SEEN.remove(key);
					continue;
				}
				HostDig.DugColumn column = chunk.getAttached(HostDig.DUG);
				if (column == null) {
					column = NONE;
				}
				HostDig.DugColumn previous = SEEN.get(key);
				if (previous == column && !worldChanged) {
					continue;
				}
				SEEN.put(key, column);
				for (HostDig.DugColumn c : new HostDig.DugColumn[] { column, previous == null ? NONE : previous }) {
					for (HostDig.DugSection s : c.sections()) {
						if (worldChanged || s.world() == world) {
							// Its walls, and the walls next door (a dug cell can open one up).
							WorldExporter.markDirtyNow(cx, s.sectionY(), cz);
							WorldExporter.markDirty(cx - 1, s.sectionY(), cz);
							WorldExporter.markDirty(cx + 1, s.sectionY(), cz);
							WorldExporter.markDirty(cx, s.sectionY() - 1, cz);
							WorldExporter.markDirty(cx, s.sectionY() + 1, cz);
							WorldExporter.markDirty(cx, s.sectionY(), cz - 1);
							WorldExporter.markDirty(cx, s.sectionY(), cz + 1);
						}
					}
				}
			}
		}
		if (SEEN.size() > 8192) {
			SEEN.clear();
		}
	}
}
