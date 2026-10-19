package dev.hollowcraft.world;

/** Native jump phases advance at host physics boundaries; Minecraft owns collision and item ticks. */
public final class CalibratedMotion {
    public static final int JUMP = 1 << 24, DOUBLE_JUMP = 1 << 25, STATE_MASK = 0x03ffffff;
    private double velocityY, remainingStep, elapsed, hold, minimum, doubleHold, delay, impulse;
    private double releaseAt = Double.POSITIVE_INFINITY;
    private boolean jumping, airJump;
    private int jumpSteps, jumpedSteps, doubleSteps;

    public double velocityY() { return velocityY; }
    public double elapsedSeconds() { return Math.max(0, elapsed - remainingStep); }

    public void profile(double speed, double holdSeconds, double minimumSeconds, double doubleSeconds, double delaySeconds) {
        if (!Double.isFinite(speed) || speed <= 0 || speed > 1000 || !Double.isFinite(holdSeconds)
            || holdSeconds < 0 || holdSeconds > 2 || !Double.isFinite(minimumSeconds) || minimumSeconds < 0
            || minimumSeconds > holdSeconds || !Double.isFinite(doubleSeconds) || doubleSeconds < 0 || doubleSeconds > 2
            || !Double.isFinite(delaySeconds) || delaySeconds < 0 || delaySeconds > 1)
            throw new IllegalArgumentException("Invalid jump profile");
        impulse = speed; hold = holdSeconds; minimum = minimumSeconds; doubleHold = doubleSeconds; delay = delaySeconds;
    }

    public int snapshot() {
        return jumpSteps | (jumpedSteps << 8) | (doubleSteps << 16) | (jumping ? JUMP : 0) | (airJump ? DOUBLE_JUMP : 0);
    }

    public void restore(double velocity, int state) {
        if (!Double.isFinite(velocity) || (state & ~STATE_MASK) != 0) throw new IllegalArgumentException("Invalid motion state");
        velocityY = velocity; remainingStep = elapsed = 0; releaseAt = Double.POSITIVE_INFINITY;
        jumpSteps = state & 255; jumpedSteps = (state >>> 8) & 255; doubleSteps = (state >>> 16) & 255;
        jumping = (state & JUMP) != 0; airJump = (state & DOUBLE_JUMP) != 0;
    }

    public void jump(boolean airborne) {
        airJump = airborne; jumping = !airborne;
        if (airborne) doubleSteps = 0;
        else { jumpSteps = jumpedSteps = doubleSteps = 0; }
        elapsed = remainingStep = 0; releaseAt = Double.POSITIVE_INFINITY;
    }

    public void release(double age) {
        if (Double.isFinite(age) && age >= 0 && age <= 3600) releaseAt = Math.min(releaseAt, age);
    }

    public void collide(boolean grounded, boolean ceiling) {
        if (grounded || ceiling) {
            velocityY = remainingStep = 0; jumping = airJump = false; jumpSteps = doubleSteps = 0;
        }
    }

    private void cutReleasedJump(int minimumSteps) {
        if (elapsed + 1e-8 >= releaseAt && jumpedSteps >= minimumSteps && velocityY > 0) {
            velocityY = 0; jumping = false; jumpSteps = 0;
        }
    }

    public double advance(double seconds, double fixedStep, double gravity, double maxFall, boolean held) {
        if (!Double.isFinite(seconds) || seconds < 0 || seconds > .1 || !Double.isFinite(fixedStep)
            || fixedStep < .005 || fixedStep > .05 || !Double.isFinite(gravity) || gravity < 0 || gravity > 2000
            || !Double.isFinite(maxFall) || maxFall <= 0 || maxFall > 1000 || !Double.isFinite(velocityY))
            throw new IllegalArgumentException("Invalid movement profile");
        double distance = 0;
        int holdSteps = (int)Math.round(hold / fixedStep), minimumSteps = (int)Math.round(minimum / fixedStep);
        int delaySteps = (int)Math.round(delay / fixedStep), airSteps = (int)Math.round((delay + doubleHold) / fixedStep);
        if (holdSteps > 255 || airSteps > 255) throw new IllegalArgumentException("Jump counters exceed protocol range");
        if (!held && !Double.isFinite(releaseAt)) releaseAt = elapsed;
        while (seconds > 1e-9) {
            if (remainingStep <= 1e-9) {
                cutReleasedJump(minimumSteps);
                if (jumping) {
                    if (jumpSteps < holdSteps) { velocityY = impulse; jumpSteps++; jumpedSteps++; }
                    else { jumping = false; jumpSteps = 0; }
                }
                if (airJump) {
                    if (doubleSteps < airSteps) {
                        if (doubleSteps >= delaySteps) velocityY = impulse * 1.1;
                        doubleSteps++;
                    } else { airJump = false; doubleSteps = 0; }
                }
                elapsed += fixedStep;
                velocityY = Math.max(-maxFall, velocityY - gravity * fixedStep);
                remainingStep = fixedStep;
            }
            double step = Math.min(seconds, remainingStep);
            distance += velocityY * step; seconds -= step; remainingStep -= step;
            // Native Update cuts upward speed after physics, but does not cancel the double-jump impulse window.
            if (remainingStep <= 1e-9) cutReleasedJump(minimumSteps);
        }
        return distance;
    }
}
