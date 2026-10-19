package dev.hollowcraft.world;

import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;
import org.junit.jupiter.api.Test;

class HostTriCellTest {
    @Test void retainsThinNativeSurfacesAndRejectsEmptyTriangleBounds() {
        var floor = new HostTri(new float[] {0,14.048f,-3, 20,14.048f,-3, 20,14.048f,3}, 0, false);
        assertTrue(floor.intersectsCell(15,14,0), "A floor below the first volume sample still occupies its cell");
        assertFalse(floor.intersectsCell(15,13,0), "A surface alone is not the volume below it");
        var wall = new HostTri(new float[] {4.02f,0,-3, 4.02f,20,-3, 4.02f,20,3}, 0, false);
        assertTrue(wall.intersectsCell(4,15,0));
        assertFalse(wall.intersectsCell(5,15,0));
        var corner = new HostTri(new float[] {0,0,0, 2,0,0, 0,2,0}, 0, false);
        assertFalse(corner.intersectsCell(2,2,0), "Overlapping AABBs do not prove a triangle intersection");
        assertTrue(corner.intersectsCell(0,0,0));
    }
}
