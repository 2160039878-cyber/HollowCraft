"""Attach the game's separate original AudioClip to a watchable movie, preserving video packets."""
import argparse
from array import array
import hashlib
import json
import math
from pathlib import Path
import subprocess


def mux_preview(ffmpeg, video, audio, output):
    ffmpeg, video, audio, output = map(Path, (ffmpeg, video, audio, output))
    probe = ffmpeg.with_name('ffprobe' + ffmpeg.suffix)
    for path in (ffmpeg, probe, video, audio):
        if not path.is_file(): raise FileNotFoundError(path)
    if output.resolve() in (video.resolve(), audio.resolve()):
        raise ValueError('Preview must not replace the game video or original AudioClip')

    def metadata(path):
        return json.loads(subprocess.run([str(probe), '-v', 'error', '-show_streams',
            '-show_format', '-of', 'json', str(path)], check=True, capture_output=True, text=True).stdout)

    source = metadata(video)
    source_video = next(s for s in source['streams'] if s['codec_type'] == 'video')
    duration = source['format']['duration']
    if not output.exists():
        output.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run([str(ffmpeg), '-hide_banner', '-loglevel', 'error', '-n',
            '-i', str(video), '-i', str(audio), '-map', '0:v:0', '-map', '1:a:0',
            '-c:v', 'copy', '-c:a', 'aac', '-b:a', '192k', '-af', 'apad',
            '-t', duration, '-movflags', '+faststart', str(output)], check=True)
    target = metadata(output)
    target_video = next(s for s in target['streams'] if s['codec_type'] == 'video')
    target_audio = next(s for s in target['streams'] if s['codec_type'] == 'audio')
    for field in ('width', 'height', 'nb_frames', 'r_frame_rate', 'duration'):
        assert target_video[field] == source_video[field], (field, source_video[field], target_video[field])
    assert abs(float(target['format']['duration']) - float(duration)) < .04, 'Movie duration changed'

    def video_hash(path):
        return subprocess.run([str(ffmpeg), '-v', 'error', '-i', str(path), '-map', '0:v:0',
            '-c:v', 'copy', '-f', 'hash', '-hash', 'sha256', '-'],
            check=True, capture_output=True, text=True).stdout.strip()

    packet_hash = video_hash(video)
    assert video_hash(output) == packet_hash, 'Video packets changed'

    def waveform(path):
        data = subprocess.run([str(ffmpeg), '-v', 'error', '-i', str(path), '-map', '0:a:0',
            '-af', 'apad', '-t', duration, '-ac', '1', '-ar', '8000', '-f', 'f32le', '-'],
            check=True, capture_output=True).stdout
        result = array('f'); result.frombytes(data)
        return result

    original, decoded = waveform(audio), waveform(output)
    assert abs(len(original) - len(decoded)) <= 8, 'Audio timeline changed'
    count = min(len(original), len(decoded)); assert count > 0
    energy = sum(x*x for x in original[:count]); assert energy/count > 1e-10, 'Original AudioClip is silent'
    decoded_energy = sum(x*x for x in decoded[:count]); assert decoded_energy > 0, 'Preview is silent'
    cross = sum(x*y for x,y in zip(original, decoded))
    correlation = cross / math.sqrt(energy * decoded_energy)
    relative_error = math.sqrt(sum((x-y)**2 for x,y in zip(original, decoded)) / energy)
    assert correlation > .99 and relative_error < .12, (correlation, relative_error)
    with audio.open('rb') as stream: audio_sha = hashlib.file_digest(stream, 'sha256').hexdigest()
    report = {'video': str(video.resolve()), 'originalAudioClip': str(audio.resolve()),
        'originalAudioSha256': audio_sha, 'output': str(output.resolve()),
        'duration': target['format']['duration'], 'frames': int(target_video['nb_frames']),
        'videoPacketSha256': packet_hash.split('=',1)[1], 'videoPacketsUnchanged': True,
        'audioCodec': target_audio['codec_name'], 'channels': target_audio['channels'],
        'waveformCorrelation': correlation, 'relativeWaveformError': relative_error,
        'decodedRmsDb': 10*math.log10(decoded_energy/count),
        'timing': 'Original AudioClip starts at0; pad or stop at original movie duration, without changing speed or volume.',
        'checksPassed': True}
    output.with_suffix('.audio.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    for name in ('ffmpeg', 'video', 'audio', 'out'): parser.add_argument('--'+name, type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(mux_preview(args.ffmpeg, args.video, args.audio, args.out)))
