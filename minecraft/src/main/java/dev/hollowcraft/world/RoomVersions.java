package dev.hollowcraft.world;

import com.mojang.serialization.Codec;
import com.mojang.serialization.codecs.RecordCodecBuilder;
import java.util.HashMap;
import java.util.Map;
import net.minecraft.server.MinecraftServer;
import net.minecraft.resources.Identifier;
import net.minecraft.world.level.saveddata.SavedData;
import net.minecraft.world.level.saveddata.SavedDataType;

/** Local integrated-server state: restoring a room invalidates old holes, including unloaded chunks. */
public final class RoomVersions extends SavedData {
    private record Reset(int version, String request) {
        private static final Codec<Reset> CODEC = RecordCodecBuilder.create(i -> i.group(
            Codec.intRange(0,Integer.MAX_VALUE).fieldOf("version").forGetter(Reset::version),
            Codec.STRING.fieldOf("request").forGetter(Reset::request)).apply(i,Reset::new));
    }
    static final Codec<RoomVersions> CODEC = Codec.unboundedMap(Codec.STRING,Reset.CODEC)
        .xmap(RoomVersions::new, data -> data.rooms);
    private static final SavedDataType<RoomVersions> TYPE = new SavedDataType<>(
        Identifier.fromNamespaceAndPath("hollowcraft","room_versions"), () -> new RoomVersions(Map.of()),CODEC,null);
    private final Map<String,Reset> rooms;
    private static volatile Map<Integer,Integer> current = Map.of();
    RoomVersions() { this(Map.of()); }

    private RoomVersions(Map<String,Reset> rooms) {
        if (rooms.size()>4096) throw new IllegalArgumentException("Too many room revisions");
        for (var entry : rooms.entrySet()) {
            int world=Integer.parseInt(entry.getKey());
            if (world<1 || world>4096 || !entry.getValue().request().matches("[a-f0-9]{32}"))
                throw new IllegalArgumentException("Invalid saved room revision");
        }
        this.rooms=new HashMap<>(rooms);
    }
    private void publish() {
        var versions=new HashMap<Integer,Integer>();
        rooms.forEach((world,reset) -> versions.put(Integer.parseInt(world),reset.version()));
        current=Map.copyOf(versions);
    }
    public static void load(MinecraftServer server) { server.overworld().getDataStorage().computeIfAbsent(TYPE).publish(); }
    public static int current(int world) { return current.getOrDefault(world,0); }
    public static int restore(MinecraftServer server,int world,String request) {
        return server.overworld().getDataStorage().computeIfAbsent(TYPE).restore(world,request);
    }
    int restore(int world,String request) {
        if (world<1 || world>4096 || request==null || !request.matches("[a-f0-9]{32}"))
            throw new IllegalArgumentException("Invalid room restore identity");
        String key=Integer.toString(world);
        Reset previous=rooms.get(key);
        if(previous!=null && previous.request().equals(request)) return previous.version();
        int version=Math.addExact(previous==null?0:previous.version(),1);
        rooms.put(key,new Reset(version,request));
        setDirty(); publish();
        return version;
    }
}
