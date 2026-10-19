package dev.hollowcraft.world;

import static org.junit.jupiter.api.Assertions.*;
import org.junit.jupiter.api.Test;

final class CalibratedMotionTest {
    @Test void matchesNativeHeldJumpApexAndCutsReleasedJumpWithoutRefreshingAirState() {
        double speed=22, gravity=60, fixed=.02, hold=.20;
        var motion=new CalibratedMotion();
        motion.profile(speed,hold,.06,.12,.08);motion.restore(0,0);motion.jump(false);
        double position=0,peak=0;
        for(int i=0;i<40;i++) { position+=motion.advance(.05,fixed,gravity,40,true);peak=Math.max(peak,position); }
        int ascent=(int)Math.floor(speed/(gravity*fixed));
        double nativePeak=((hold/fixed-1)*(speed-gravity*fixed)+ascent*speed-gravity*fixed*ascent*(ascent+1)/2)*fixed;
        assertEquals(nativePeak,peak,.025);
        motion.restore(0,0);motion.jump(false);
        position=motion.advance(.05,fixed,gravity,40,true);
        position+=motion.advance(.05,fixed,gravity,40,false);
        assertTrue(position<peak/2);
        assertTrue(motion.velocityY()<=0);
        motion.restore(-5,0);
        assertTrue(motion.advance(.05,fixed,gravity,40,true)<0, "Switching items cannot create a new jump");
        motion.collide(true,false);assertEquals(0,motion.velocityY());
        assertThrows(IllegalArgumentException.class,()->motion.advance(.05,Double.NaN,gravity,40,true));
    }

    @Test void releaseAtObservedPhysicsBoundaryDoesNotAddAnotherImpulse() {
        for (int heldTicks : new int[]{4,6,15}) {
            var motion=new CalibratedMotion();
            motion.profile(22,.20,.06,.12,.08);motion.restore(0,0);motion.jump(false);
            motion.release(heldTicks*.02);
            double distance=0,expected=0,velocity=0;
            for(int tick=0;tick<heldTicks;tick++) {
                if(tick<10) velocity=22;
                velocity-=60*.02;expected+=velocity*.02;
                distance+=motion.advance(.02,.02,60,40,true);
            }
            assertEquals(expected,distance,1e-8);
            assertEquals(0,motion.velocityY(),1e-8);
            assertTrue(motion.advance(.02,.02,60,40,true)<0);
        }
    }

    @Test void releasingDoubleJumpPreservesAllSixNativeImpulseSteps() {
        var motion=new CalibratedMotion();
        motion.profile(22,.20,.06,.12,.08);motion.restore(-2,10<<8);motion.jump(true);
        motion.release(.08);
        double distance=0;
        for(int tick=0;tick<4;tick++) distance+=motion.advance(.02,.02,60,40,true);
        double beforeImpulse=distance;
        for(int tick=0;tick<6;tick++) {
            distance+=motion.advance(.02,.02,60,40,true);
            assertEquals(0,motion.velocityY(),1e-8);
        }
        assertEquals(6*(24.2-60*.02)*.02,distance-beforeImpulse,1e-8);
        assertTrue(motion.advance(.02,.02,60,40,true)<0);
    }

    @Test void repeatedHandoffsPreserveImpulseCountersAndReleasedBallisticMotion() {
        for(boolean airborne:new boolean[]{false,true}) for(double release:new double[]{.12,Double.POSITIVE_INFINITY}) {
            var uninterrupted=new CalibratedMotion();
            var transferred=new CalibratedMotion();
            for(var motion:new CalibratedMotion[]{uninterrupted,transferred}) {
                motion.profile(22,.20,.06,.12,.08);
                motion.restore(airborne?-2:0,airborne?10<<8:0);motion.jump(airborne);
                motion.release(release);
            }
            for(int tick=0;tick<60;tick++) {
                if(tick%3==0) {
                    transferred.restore(transferred.velocityY(),transferred.snapshot());
                    transferred.release(Math.max(0,release-tick*.02));
                }
                assertEquals(uninterrupted.advance(.02,.02,60,40,true),transferred.advance(.02,.02,60,40,true),1e-8);
                assertEquals(uninterrupted.velocityY(),transferred.velocityY(),1e-8);
                assertEquals(uninterrupted.snapshot(),transferred.snapshot());
            }
        }
        assertThrows(IllegalArgumentException.class,()->new CalibratedMotion().restore(0,0x40000000));
    }
}
