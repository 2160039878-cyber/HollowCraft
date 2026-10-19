"""Check real shared-memory deadline, cold-bow and disconnected-peer evidence."""
import json
import sys
from pathlib import Path


def check(root):
    def read(name):
        return json.loads((root/(name+'.json')).read_text(encoding='utf-8-sig'))

    before=read('delayed-poll-before-runtime')
    late=before['LastPhysicsTimeout']
    assert before['PhysicsTimeouts']==1
    assert late['polls']==1 and late['finalPollGapMilliseconds']>=80
    assert late['lateRead'] and late['lateScopeMatches']
    assert (late['lateTick'],late['lateControl'],late['lateTeleport'])==(
        late['expectedTick'],late['expectedControl'],late['expectedTeleport'])
    assert read('delayed-poll-before')['reason']=='Minecraft physics timed out'

    after=read('delayed-poll-after-runtime')
    probe=read('delayed-poll-after')
    steps=read('delayed-poll-after-input')
    assert len(steps)==5 and all(s['PhysicsPollDelay']==80 for s in steps)
    assert probe.get('complete') and {s['step'] for s in probe['samples']}==set(range(5))
    assert after['PhysicsTimeouts']==0 and after['LastPhysicsTimeout'] is None
    assert after['MaxPhysicsWaitMilliseconds']>=80 and after['ready']
    assert all(s['hp']==5 and abs(s['x']-132.38)<.001 and abs(s['y']-11.411025)<.001 for s in probe['samples'])
    observed=list(probe['samples'])

    cold=[]
    for label in ['baseline-01','baseline-02','fixed-unprofiled-01']:
        runtime=read('runtime-'+label)
        bow=read('bow-'+label)
        assert bow.get('complete') and runtime['PhysicsTimeouts']==0
        assert {s['step'] for s in bow['samples']}==set(range(28))
        hits=[h for h in bow['hits'] if h['name']=='Absolute Radiance' and h['before']>h['after']]
        assert hits and all(h['attackType']=='Generic' for h in hits)
        observed.extend(bow['samples'])
        cold.append(dict(label=label,completedAttackCycles=14,damageHits=len(hits),
            damage=sum(h['before']-h['after'] for h in hits),maxWaitMilliseconds=runtime['MaxPhysicsWaitMilliseconds']))

    lost=read('peer-loss-active')
    active=read('peer-loss-active-runtime')
    before_loss=read('peer-loss-before')
    after_loss=read('peer-loss-after')
    settled=read('peer-loss-settled')
    assert active['BackgroundInput'] and not active['native'] and active['moveX']<0
    assert lost.get('cancelled') and lost['reason']=='Minecraft physics timed out'
    assert after_loss['PhysicsTimeouts']==before_loss['PhysicsTimeouts']+1
    assert not after_loss['connected'] and not after_loss['ready']
    assert after_loss['pausedByBridge'] and after_loss['timeScale']==0
    assert (after_loss['heroX'],after_loss['heroY'])==(settled['heroX'],settled['heroY'])
    timeout=after_loss['LastPhysicsTimeout']
    assert timeout['lateTick']!=timeout['expectedTick'] and timeout['elapsed']>=40
    observed.extend(lost['samples'])
    assert observed and all(s['HiddenWindow'] and s['visibleWindows']==0 and not s['ownsForegroundWindow'] for s in observed)
    return dict(passed=True,lateReplyBefore=dict(falseTimeouts=1,delayMilliseconds=late['finalPollGapMilliseconds']),
        lateReplyAfter=dict(completedDelaySteps=5,timeouts=0,maxWaitMilliseconds=after['MaxPhysicsWaitMilliseconds']),
        coldBow=cold,peerLoss=dict(timeoutMilliseconds=timeout['elapsed'],paused=True,positionStableSeconds=2),
        hiddenSamples=len(observed),limitations=[
            'The two original intermittent first-bow stalls were not reproduced; their cause remains unproven.',
            'Baseline-02 needed an idle probe to finish initial loading; its first bow remained unused until the resumed run.',
            'Radiance fixture bypasses early combat and protects the player; this is synchronization and outgoing-hit validation.',
            'Hidden probes and injected delays do not establish 1080p FPS or redstone/TNT stress acceptance.'])


if __name__=='__main__':
    print(json.dumps(check(Path(sys.argv[1])),indent=2))
