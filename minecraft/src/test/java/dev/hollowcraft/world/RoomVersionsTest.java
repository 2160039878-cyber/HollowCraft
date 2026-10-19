package dev.hollowcraft.world;

import static org.junit.jupiter.api.Assertions.*;
import com.mojang.serialization.JsonOps;
import org.junit.jupiter.api.Test;

final class RoomVersionsTest {
    @Test void restoresOnlyRequestedRoomAndSurvivesSerialization() {
        String first="11111111111111111111111111111111", second="22222222222222222222222222222222";
        RoomVersions data=new RoomVersions();
        assertEquals(1,data.restore(1,first));
        assertEquals(1,data.restore(1,first));
        assertEquals(0,RoomVersions.current(2));
        assertEquals(1,data.restore(2,first));
        var encoded=RoomVersions.CODEC.encodeStart(JsonOps.INSTANCE,data).getOrThrow();
        RoomVersions restored=RoomVersions.CODEC.parse(JsonOps.INSTANCE,encoded).getOrThrow();
        assertEquals(1,restored.restore(1,first));
        assertEquals(2,restored.restore(1,second));
        assertEquals(1,RoomVersions.current(2));
        assertThrows(IllegalArgumentException.class,()->restored.restore(4097,first));
        assertThrows(IllegalArgumentException.class,()->restored.restore(1,"../room"));
    }
}
