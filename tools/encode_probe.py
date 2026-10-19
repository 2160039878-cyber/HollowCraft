"""Encode real Unity probe frames and the native listener recording at their recorded times."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile


def frame_times(samples):
    times = {}
    for sample in samples:
        index = sample.get('captureIndex', 0) - 1
        if index >= 0:
            times.setdefault(index, sample['t'])
    return times


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('probe', type=Path)
    parser.add_argument('output', type=Path)
    parser.add_argument('--ffmpeg', required=True, type=Path)
    parser.add_argument('--allow-cancelled', action='store_true', help='Export captured frames from an interrupted or scene-ended probe; preserve its cancellation reason.')
    args = parser.parse_args()
    metadata = args.output.with_suffix('.video.json')
    if metadata.resolve() == args.probe.resolve():
        parser.error('Video metadata would overwrite the source probe')
    probe = json.loads(args.probe.read_text(encoding='utf-8-sig'))
    assert (probe.get('complete') or args.allow_cancelled and probe.get('cancelled')) and probe['captureDirectory']
    captures = Path(probe['captureDirectory'])
    times = {frame['index']:frame['t'] for frame in probe['captures']} if probe.get('captures') else frame_times(probe['samples'])
    indices = sorted(times)
    assert indices and indices[0] == 0
    omitted = sorted(set(range(indices[-1]+1))-set(indices))
    audio = probe.get('audio')
    if audio:
        assert audio['format'] == 'f32le' and not audio['error'] and not audio['overflow'] and not audio['channelsChanged']
        assert 8000 <= audio['sampleRate'] <= 192000 and 1 <= audio['channels'] <= 8
        assert audio['samples'] > 0 and Path(audio['path']).stat().st_size == audio['samples'] * 4
        assert abs(audio['timingErrorSeconds']) < .1, 'Audio clock gap exceeds capture tolerance'
    assert frame_times([{'captureIndex':1,'t':0},{'captureIndex':1,'t':.01},{'captureIndex':2,'t':.05}]) == {0:0,1:.05}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='hollowcraft-video-', dir=Path.cwd()) as temp:
        concat = Path(temp) / 'frames.txt'
        lines = []
        for position,i in enumerate(indices):
            path = captures / f'{i:05}.png'
            with path.open('rb') as stream:
                assert stream.read(8) == b'\x89PNG\r\n\x1a\n', f'Incomplete capture: {path}'
            duration = times[indices[position+1]]-times[i] if position+1 < len(indices) else .05
            assert 0 < duration < 120
            escaped = path.resolve().as_posix().replace("'", "'\\''")
            lines.extend([f"file '{escaped}'", f'duration {duration:.6f}'])
        lines.append(lines[-2])
        concat.write_text('\n'.join(lines)+'\n', encoding='utf-8')
        command = [str(args.ffmpeg),'-hide_banner','-loglevel','error','-n','-f','concat','-safe','0','-i',str(concat)]
        if audio:
            offset = audio['startOffsetSeconds'] - times[indices[0]]
            command += ['-ss' if offset < 0 else '-itsoffset', f'{abs(offset):.6f}',
                        '-f','f32le','-ar',str(audio['sampleRate']),'-ac',str(audio['channels']),'-i',audio['path'],
                        '-map','0:v:0','-map','1:a:0','-c:a','aac','-b:a','192k','-af','apad',
                        '-t',f'{times[indices[-1]]-times[indices[0]]+.05:.6f}']
        command += ['-fps_mode','vfr','-c:v','libx264','-bf','0','-preset','medium','-crf','20','-pix_fmt','yuv420p',
                    '-movflags','+faststart',str(args.output)]
        subprocess.run(command,check=True)
    result = {'frames':len(indices),'source':str(args.probe),'durationApprox':times[indices[-1]]-times[0]+.05,'omittedFramesWithoutTimestamp':omitted,
              'sha256':hashlib.sha256(args.output.read_bytes()).hexdigest(),
              'audio':audio,'sourceCompleted':bool(probe.get('complete')),'sourceCancellationReason':probe.get('reason'),
              'note':('Real in-game frames and native HK listener audio; Minecraft process audio is not recorded.' if audio else 'Real in-game frames; source probe has no audio.')
                     +' Capture overhead excludes this run from performance acceptance.'}
    metadata.write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps(result))


if __name__ == '__main__':
    main()
