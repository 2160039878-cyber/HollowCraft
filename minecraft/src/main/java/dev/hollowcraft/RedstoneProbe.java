package dev.hollowcraft;

import com.google.gson.Gson;
import dev.hollowcraft.link.HostLink;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.Map;
import net.minecraft.core.BlockPos;
import net.minecraft.core.Direction;
import net.minecraft.server.MinecraftServer;
import net.minecraft.server.level.ServerLevel;
import net.minecraft.world.level.block.Blocks;
import net.minecraft.world.level.block.LeverBlock;
import net.minecraft.world.level.block.RepeaterBlock;
import net.minecraft.world.level.block.state.properties.AttachFace;
import net.minecraft.world.level.block.state.properties.BlockStateProperties;

/** Development acceptance fixture: real blocks, a real lever update, native redstone ticks and TNT fuse. */
public final class RedstoneProbe {
    private static final boolean ENABLED = Boolean.getBoolean("hollowcraft.testMode");
    private static final Path REQUEST = Path.of("hollowcraft-fixture.request");
    private static final Path RESULT = Path.of("hollowcraft-fixture-result.json");
    private static final ArrayList<Map<String, Object>> events = new ArrayList<>();
    private static ServerLevel level;
    private static BlockPos lever, repeater, tnt;
    private static long start, nextPoll;
    private static int world;
    private static HostLink.Scope fixtureScope;
    private static boolean pulled, powered;
    private static int tntCount;
    private static boolean stress, armed, finisher;
    private static boolean previousTargeted;
    private static long lastToggle;
    private static final ArrayList<BlockPos> stressLevers = new ArrayList<>(), components = new ArrayList<>(), explosives = new ArrayList<>();
    private RedstoneProbe() { }

    public static void tick(MinecraftServer server) {
        if (!ENABLED || !HostLink.active()) return;
        HostLink.HostState host = new HostLink.HostState();
        if (!HostLink.readSkyState(host)) return;
        try {
            if (level != null && !host.scope().equals(fixtureScope)) {
                record("aborted", Map.of("reason", "scope changed")); level = null;
            }
            if (!host.inGame() || host.loading() || host.menuOpen()) return;
            if (level == null && System.currentTimeMillis() >= nextPoll) {
                nextPoll = System.currentTimeMillis() + 1000;
                if (!Files.exists(REQUEST)) return;
                if (Files.size(REQUEST) > 64) throw new IllegalArgumentException("Oversized redstone fixture");
                String request = Files.readString(REQUEST).trim();
                String[] fields=request.split("\\s+");
                finisher=fields.length==3 && fields[0].equals("redstone-finish");
                boolean positioned=fields.length==3 && (fields[0].equals("redstone-at") || finisher);
                int fixtureX=0,fixtureY=0;
                if(positioned) {
                    fixtureX=Integer.parseInt(fields[1]);fixtureY=Integer.parseInt(fields[2]);
                    if(Math.abs(fixtureX-host.x)>64 || Math.abs(fixtureY-host.y)>64)
                        throw new IllegalArgumentException("Fixture target is outside the loaded player neighbourhood");
                }
                if (!positioned && !request.equals("redstone") && !request.equals("redstone-chain") && !request.equals("redstone-stress"))
                    throw new IllegalArgumentException("Unknown redstone fixture");
                boolean repeat=positioned && previousTargeted && fixtureScope!=null && fixtureScope.equals(host.scope())
                    && lever!=null && lever.getX()==fixtureX && lever.getY()==fixtureY;
                previousTargeted=positioned;
                stress=request.equals("redstone-stress");armed=!stress;
                tntCount = finisher || request.equals("redstone-chain") || stress ? 20 : 1;
                Files.delete(REQUEST);
                if (server.getPlayerList().getPlayers().isEmpty()) return;
                level = server.getPlayerList().getPlayers().getFirst().level();
                world = host.worldId;
                fixtureScope = host.scope();
                if(stress) {
                    buildStress(host);
                    return;
                }
                lever = positioned ? new BlockPos(fixtureX,fixtureY,(int)Math.floor(host.z))
                    : BlockPos.containing(Math.floor(host.x) + 2, Math.ceil(host.y), host.z);
                repeater = lever.east(3); tnt = lever.east(5);
                int width=5+tntCount+(finisher ? 4 : 0);
                if(positioned) for(int i=0;i<width;i++) {
                    var cell=lever.east(i);
                    var expected=i==0 ? Blocks.LEVER : i==3 ? Blocks.REPEATER : i==5 ? Blocks.TNT : Blocks.REDSTONE_WIRE;
                    if((!level.isEmptyBlock(cell) && !(repeat && level.getBlockState(cell).is(expected)))
                        || (!level.isEmptyBlock(cell.below()) && !(repeat && level.getBlockState(cell.below()).is(Blocks.STONE)))
                        || !dev.hollowcraft.world.HostCollision.isKnown(cell.getX(),cell.getY(),cell.getZ())
                        || dev.hollowcraft.world.HostCollision.hasGeometry(cell))
                        throw new IllegalStateException("Targeted redstone area is occupied or not streamed");
                }
                for (int i = 0; i < width; i++) level.setBlock(lever.east(i).below(), (finisher ? Blocks.OBSIDIAN : Blocks.STONE).defaultBlockState(), 3);
                level.setBlock(lever, Blocks.LEVER.defaultBlockState()
                    .setValue(BlockStateProperties.ATTACH_FACE, AttachFace.FLOOR)
                    .setValue(BlockStateProperties.HORIZONTAL_FACING, Direction.EAST), 3);
                level.setBlock(lever.east(), Blocks.REDSTONE_WIRE.defaultBlockState(), 3);
                level.setBlock(lever.east(2), Blocks.REDSTONE_WIRE.defaultBlockState(), 3);
                level.setBlock(repeater, Blocks.REPEATER.defaultBlockState()
                    .setValue(BlockStateProperties.HORIZONTAL_FACING, Direction.WEST).setValue(RepeaterBlock.DELAY, 2), 3);
                level.setBlock(lever.east(4), Blocks.REDSTONE_WIRE.defaultBlockState(), 3);
                for (int i = 0; i < tntCount; i++) level.setBlock(tnt.east(i), Blocks.TNT.defaultBlockState(), 3);
                start = level.getGameTime(); pulled = powered = false; events.clear();
                record("built", Map.of("lever", position(lever), "repeater", position(repeater), "tnt", position(tnt), "tntCount", tntCount, "world", host.worldId));
            }
            if (level == null) return;
            if(stress && !armed) {
                if(!Files.exists(REQUEST)) return;
                if(Files.size(REQUEST)>64 || !Files.readString(REQUEST).trim().equals("redstone-fire"))
                    throw new IllegalArgumentException("Stress fixture expects redstone-fire");
                Files.delete(REQUEST);armed=true;start=level.getGameTime();lastToggle=-20;
                record("armed",Map.of("components",componentCount(),"tntCount",remainingTnt()));
            }
            long age = level.getGameTime() - start;
            if(stress) {
                if(age-lastToggle>=20) {
                    int toggled=0;
                    for(var pos:stressLevers) if(level.getBlockState(pos).is(Blocks.LEVER)) {
                        ((LeverBlock)Blocks.LEVER).pull(level.getBlockState(pos),level,pos,server.getPlayerList().getPlayers().getFirst());toggled++;
                    }
                    lastToggle=age;record("toggle",Map.of("levers",toggled,"components",componentCount()));
                }
                if(age%20==10) {
                    int active=0;
                    for(var pos:components) {
                        var state=level.getBlockState(pos);
                        if(state.is(Blocks.REDSTONE_WIRE) && state.getValue(BlockStateProperties.POWER)>0
                            || (state.is(Blocks.LEVER) || state.is(Blocks.REPEATER)) && state.getValue(BlockStateProperties.POWERED)) active++;
                    }
                    record("power",Map.of("powered",active));
                }
                if(age>=360) {record("finished",Map.of("components",componentCount(),"remaining",remainingTnt()));level=null;}
                return;
            }
            if (!pulled && age >= (finisher ? 0 : 40)) {
                ((LeverBlock)Blocks.LEVER).pull(level.getBlockState(lever), level, lever, server.getPlayerList().getPlayers().getFirst());
                pulled = true; record("lever-on", Map.of());
            }
            var state = level.getBlockState(repeater);
            if (!powered && state.is(Blocks.REPEATER) && state.getValue(BlockStateProperties.POWERED)) {
                powered = true; record("repeater-on", Map.of());
            }
            if (age >= (tntCount == 1 ? 180 : 360)) {
                int remaining = 0;
                for (int i = 0; i < tntCount; i++) if (level.getBlockState(tnt.east(i)).is(Blocks.TNT)) remaining++;
                record("finished", Map.of("powered", powered, "tntBlockRemaining", remaining != 0, "remaining", remaining)); level = null;
            }
        } catch (Exception error) {
            HollowCraft.LOG.error("Redstone probe failed", error); level = null;
        }
    }

    private static void buildStress(HostLink.HostState host) {
        stressLevers.clear();components.clear();explosives.clear();events.clear();
        lever=BlockPos.containing(Math.floor(host.x)-22,Math.ceil(host.y)+2,host.z);
        repeater=lever.east(13);tnt=lever.east(32);
        for(int row=0;row<8;row++) for(int col=0;col<32;col++) {
            var pos=lever.offset(col,row*2,0);components.add(pos);
            if(!level.isEmptyBlock(pos) || !level.isEmptyBlock(pos.below()))
                throw new IllegalStateException("Stress build area contains existing Minecraft blocks");
        }
        for(int i=0;i<20;i++) {
            var pos=tnt.offset(i%4,i/4,0);explosives.add(pos);
            if(!level.isEmptyBlock(pos)) throw new IllegalStateException("TNT build area occupied");
        }
        for(var pos:components) level.setBlock(pos.below(),Blocks.STONE.defaultBlockState(),3);
        for(int row=0;row<8;row++) for(int col=0;col<32;col++) {
            var pos=lever.offset(col,row*2,0);
            if(col==0) {
                level.setBlock(pos,Blocks.LEVER.defaultBlockState().setValue(BlockStateProperties.ATTACH_FACE,AttachFace.FLOOR)
                    .setValue(BlockStateProperties.HORIZONTAL_FACING,Direction.EAST),3);stressLevers.add(pos);
            } else if(col==13 || col==27) {
                level.setBlock(pos,Blocks.REPEATER.defaultBlockState().setValue(BlockStateProperties.HORIZONTAL_FACING,Direction.WEST)
                    .setValue(RepeaterBlock.DELAY,2),3);
            } else level.setBlock(pos,Blocks.REDSTONE_WIRE.defaultBlockState(),3);
        }
        for(var pos:explosives) level.setBlock(pos,Blocks.TNT.defaultBlockState(),3);
        start=level.getGameTime();
        record("built",Map.of("world",host.worldId,"components",componentCount(),"tntCount",remainingTnt(),
            "min",position(lever.below()),"max",position(lever.offset(36,15,1)),"lever",position(lever),"tnt",position(tnt)));
    }
    private static int componentCount() {
        int count=0;
        for(var pos:components) {
            var state=level.getBlockState(pos);
            if(state.is(Blocks.LEVER) || state.is(Blocks.REDSTONE_WIRE) || state.is(Blocks.REPEATER))count++;
        }
        return count;
    }
    private static int remainingTnt() {
        int count=0;for(var pos:explosives) if(level.getBlockState(pos).is(Blocks.TNT))count++;return count;
    }

    public static void exploded(double x, double y, double z, float power) {
        if (ENABLED && level != null) {
            var dug = new ArrayList<int[]>();
            for (int dx = -3; dx <= 3; dx++) for (int dy = -4; dy <= 0; dy++) {
                BlockPos p = tnt.offset(dx, dy, 0);
                if (dev.hollowcraft.world.HostDig.isDug(level, world, p)) dug.add(position(p));
            }
            record("exploded", Map.of("x", x, "y", y, "z", z, "power", power, "dugCellsAtPlane", dug));
        }
    }
    private static int[] position(BlockPos p) { return new int[] {p.getX(), p.getY(), p.getZ()}; }
    private static void record(String type, Map<String, Object> values) {
        var entry = new LinkedHashMap<String, Object>(values);
        entry.put("event", type); entry.put("tick", level.getGameTime() - start); events.add(entry);
        try { Files.writeString(RESULT, new Gson().toJson(events)); }
        catch (java.io.IOException error) { throw new java.io.UncheckedIOException(error); }
        HollowCraft.LOG.info("Redstone probe {} at tick {}", type, level.getGameTime() - start);
    }
}
