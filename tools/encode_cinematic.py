"""Encode a rendered native cinematic and verify timing and original audio preservation."""
import argparse
import hashlib
import json
import subprocess
from fractions import Fraction
from pathlib import Path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--ffmpeg', required=True, type=Path)
    parser.add_argument('--frames', required=True, type=Path)
    parser.add_argument('--reference', required=True, type=Path)
    parser.add_argument('--out', required=True, type=Path)
    args = parser.parse_args()
    ffprobe = args.ffmpeg.with_name('ffprobe' + args.ffmpeg.suffix)
    for path in (args.ffmpeg, ffprobe, args.reference):
        if not path.is_file(): raise FileNotFoundError(path)
    if args.out.exists(): raise FileExistsError(args.out)
    frames = sorted(args.frames.glob('[0-9][0-9][0-9][0-9][0-9].png'))
    assert frames and [p.name for p in frames] == [f'{i:05}.png' for i in range(1, len(frames)+1)], 'Noncontiguous frame sequence'

    def probe(path, *options):
        result = subprocess.run([str(ffprobe), '-v', 'error', *options, '-of', 'json', str(path)], check=True, capture_output=True, text=True)
        return json.loads(result.stdout)

    source = probe(args.reference, '-show_streams', '-show_format')
    video = next(s for s in source['streams'] if s['codec_type'] == 'video')
    fps = Fraction(video['r_frame_rate'])
    args.out.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run([str(args.ffmpeg), '-hide_banner', '-loglevel', 'warning', '-n',
        '-framerate', str(fps), '-start_number', '1', '-i', str(args.frames/'%05d.png'),
        '-i', str(args.reference), '-map', '0:v:0', '-map', '1:a?', '-c:v', 'libx264',
        '-crf', '16', '-preset', 'medium', '-bf', '0',
        '-vf', 'scale=in_range=pc:out_range=tv:out_color_matrix=bt709,format=yuv420p,setparams=range=limited:color_primaries=bt709:color_trc=bt709:colorspace=bt709',
        '-c:a', 'copy', '-movflags', '+faststart', str(args.out)], check=True)
    output = probe(args.out, '-show_streams', '-show_format')
    encoded = next(s for s in output['streams'] if s['codec_type'] == 'video')
    assert (encoded['width'], encoded['height']) == (video['width'], video['height'])
    assert int(encoded['nb_frames']) == len(frames) and Fraction(encoded['r_frame_rate']) == fps
    assert encoded['color_primaries'] == encoded['color_transfer'] == encoded['color_space'] == 'bt709'
    first = probe(args.out, '-select_streams', 'v:0', '-read_intervals', '%+#1', '-show_packets')['packets'][0]
    assert float(first['pts_time']) == float(first['dts_time']) == 0, 'Native Windows playback requires a zero first frame'
    audio_hash = None
    if any(s['codec_type'] == 'audio' for s in source['streams']):
        def audio(path):
            result = subprocess.run([str(args.ffmpeg), '-v', 'error', '-i', str(path), '-map', '0:a',
                '-c:a', 'copy', '-f', 'hash', '-hash', 'sha256', '-'], check=True, capture_output=True, text=True)
            return result.stdout.strip().split('=', 1)[1]
        audio_hash = audio(args.reference)
        assert audio(args.out) == audio_hash, 'Original audio packets changed or were truncated'
    duration_difference = abs(float(output['format']['duration']) - float(source['format']['duration']))
    assert duration_difference <= float(1/fps) + .001, 'Duration changed by more than one frame'
    report = {'reference': str(args.reference.resolve()), 'output': str(args.out.resolve()),
        'frames': len(frames), 'fps': str(fps), 'resolution': [encoded['width'], encoded['height']],
        'sourceDuration': source['format']['duration'], 'outputDuration': output['format']['duration'],
        'sourceAudioPacketSha256': audio_hash, 'firstFramePts': first['pts_time'],
        'sha256': hashlib.file_digest(args.out.open('rb'), 'sha256').hexdigest(), 'checksPassed': True}
    args.out.with_suffix('.encoding.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(json.dumps(report, ensure_ascii=False))


if __name__ == '__main__':
    main()
