"""Local music accent suggestions in the workbench's 30 fps timebase."""
from array import array
import math
import subprocess


def music_cues(path, duration):
    # Audio-only decode. Bound memory for long uploads; the rest of the track
    # keeps its ordinary planning behavior.
    pcm = subprocess.check_output(
        ['ffmpeg', '-v', 'error', '-nostdin', '-i', str(path), '-t', '600',
         '-vn', '-ac', '1', '-ar', '9000', '-f', 's16le', '-'], timeout=60)
    samples = array('h', pcm)
    total = math.ceil(duration * 30 - 1e-7)
    energy = [math.sqrt(sum(x*x for x in samples[i:i+300])/300)
              for i in range(0, len(samples)-299, 300)]
    peak = max(energy, default=0)
    if peak < 120:
        return [], None
    accents = []
    rises = []
    for frame in range(30, min(len(energy)-24, total-30)):
        previous = sum(energy[frame-6:frame])/6
        onset = sum(energy[frame:frame+3])/3 - previous
        if onset > max(peak*.16, previous*.55):
            accents.append((onset, frame))
        before = sum(energy[frame-24:frame])/24
        after = sum(energy[frame:frame+24])/24
        if after-before > max(peak*.18, before*.45):
            rises.append((after-before, frame))
    lift = max(rises)[1] if rises else None
    cues = [lift] if lift is not None else []
    for _, frame in sorted(accents, reverse=True):
        if len(cues) >= 3:
            break
        if all(abs(frame-other) >= 36 for other in cues):
            cues.append(frame)
    return sorted(cues), lift
