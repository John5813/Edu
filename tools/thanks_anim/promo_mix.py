"""Reklama videosi ovozi: musiqa + diktor (ElevenLabs) + personajning o'z ovozi → `audio.wav`.

- Diktor matni jimlik bo'yicha jumlalarga bo'linadi, har biri 1,1 marta tezlashtiriladi (balandligi o'zgarmaydi) va
  o'z sahnasiga qo'yiladi: shunda gap rasm bilan bir vaqtda bo'ladi.
- Personajning o'z ovozi (mushukcha) — videoning musiqasi, boshidan OXIRIGACHA to'xtamaydi — uzoqlashganda ham; 10 soniyalik ovoz
  qisqa kesishma bilan qaytariladi. U diktordan keyingi ikkinchi qatlam: diktor gapirganda sal pasayadi.
- Musiqa ham diktor gapirganda pasayadi. Yakuniy ovoz −14 LUFS, cho'qqi ≤ −1,5 dBFS.

    python tools/thanks_anim/promo_mix.py <ish_papkasi> <diktor.mp3>     # ish_papkasida music.wav bo'lishi kerak
"""
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, ROOT)
sys.path.insert(0, HERE)
import promo_music as M  # noqa: E402

SPEED = 1.1
# Jumlalar tartibi: 1 «Slaydni shunday yakunlang!»  2 «Yigirma to'rtta personaj.»  3 «Yigirma to'rtta dizayn.»
# 4 «Har biri o'z ovozi bilan.»  5 «Siz faqat tanlang,»  6 «qolganini bot qiladi!»  7 «Bu mutlaqo tekin!»  8 «Edufayl bot.»
STARTS = [0.5, 2.55, 3.95, 5.3, 6.95, 8.1, 10.1, 11.5]      # sekund: sahnaga mos (smayl, uzoqlashish, shablonlar, logo)
HERO_KEY = "tillarang_mushuk"                    # shu personajning ovozi — videoning MUSIQASI


def _sh(cmd):
    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode:
        raise RuntimeError(res.stderr[-600:])
    return res.stderr


def phrases(voice: str):
    """[(boshlanish, tugash)] — jimlik (≥0,3 s) bo'yicha; chegaralar jimlik o'rtasidan o'tadi."""
    log = _sh(["ffmpeg", "-hide_banner", "-i", voice, "-af", "silencedetect=noise=-38dB:d=0.3", "-f", "null", "-"])
    starts = [float(x) for x in re.findall(r"silence_start: ([\d.]+)", log)]
    ends = [float(x) for x in re.findall(r"silence_end: ([\d.]+)", log)]
    dur = float(subprocess.check_output(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of",
                                         "csv=p=0", voice]).decode())
    cuts = [0.0] + [(a + b) / 2 for a, b in zip(starts, ends) if a > 0.2 and b < dur - 0.2] + [dur]
    return list(zip(cuts[:-1], cuts[1:]))


def loop_audio(src: str, seconds: float, out: str, sr: int = 44100, xfade: float = 0.4) -> str:
    """`src` ovozini `seconds` gacha qaytaradi: ulanish joyida teng quvvatli kesishma (shovqinsiz)."""
    import numpy as np
    import wave

    raw = subprocess.check_output(["ffmpeg", "-v", "error", "-i", src, "-vn", "-f", "s16le", "-ac", "2", "-ar", str(sr),
                                   "-"])
    a = np.frombuffer(raw, "<i2").reshape(-1, 2).astype(np.float32) / 32768
    n, x = len(a), int(xfade * sr)
    out_len = int(seconds * sr)
    buf = np.zeros((out_len + n, 2), np.float32)
    fin = np.sin(np.linspace(0, np.pi / 2, x))[:, None]
    fout = np.cos(np.linspace(0, np.pi / 2, x))[:, None]
    pos = 0
    while pos < out_len:
        seg = a.copy()
        if pos > 0:
            seg[:x] *= fin
        if pos + n < out_len + x:                    # keyingi nusxa shu yerda kesishadi
            seg[-x:] *= fout
        buf[pos:pos + n] += seg
        pos += n - x
    buf = buf[:out_len]
    with wave.open(out, "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes((np.clip(buf, -1, 1) * 32767).astype("<i2").tobytes())
    return out


def mix(work: str, voice: str, out: str = "") -> str:
    out = out or os.path.join(work, "audio.wav")
    music = os.path.join(work, "music.wav")
    from services.thanks_anim import catalog

    cap = loop_audio(catalog.get(HERO_KEY).path("packed.mp4"), M.TOTAL, os.path.join(work, "character_loop.wav"))
    segs = phrases(voice) if voice else []
    chains, labels = [], []
    if len(segs) == len(STARTS):
        for i, ((a, b), at) in enumerate(zip(segs, STARTS)):
            ms = int(at * 1000)
            chains.append(f"[0:a]atrim={a:.3f}:{b:.3f},asetpts=PTS-STARTPTS,atempo={SPEED},"
                          f"afade=t=in:d=0.01,adelay={ms}|{ms}[p{i}]")
            labels.append(f"[p{i}]")
        voice_graph = ";".join(chains) + f";{''.join(labels)}amix=inputs={len(labels)}:normalize=0:duration=longest," \
                                         f"apad=whole_dur={M.TOTAL},atrim=0:{M.TOTAL},aformat=channel_layouts=stereo[vo]"
    elif voice:                                          # jumla soni mos kelmasa — butun matn tekis tezlashadi
        voice_graph = (f"[0:a]atempo={SPEED},adelay=500|500,apad=whole_dur={M.TOTAL},atrim=0:{M.TOTAL},"
                       "aformat=channel_layouts=stereo[vo]")
    else:
        voice_graph = f"anullsrc=r=44100:cl=stereo,atrim=0:{M.TOTAL}[vo]"
    total = M.TOTAL
    graph = (
        voice_graph + ";[vo]asplit=3[vo1][vo2][vkey];"
        # personajning o'z ovozi: boshdan oxirigacha (qaytariladi), oxirida so'nadi
        f"[1:a]aformat=channel_layouts=stereo,volume=1.0,afade=t=in:d=0.05,afade=t=out:st={total - 0.9}:d=0.9[cap];"
        "[cap][vkey]sidechaincompress=threshold=0.03:ratio=3.5:attack=10:release=300[capd];"
        "[2:a]volume=0.6[mu];[mu][vo1]sidechaincompress=threshold=0.03:ratio=4:attack=10:release=350[mud];"
        f"[mud][capd][vo2]amix=inputs=3:normalize=0:duration=longest,apad=whole_dur={total},atrim=0:{total},loudnorm=I=-14:TP=-1.5:LRA=7[o]"
    )
    _sh(["ffmpeg", "-v", "error", "-y"] + (["-i", voice] if voice else ["-f", "lavfi", "-i", "anullsrc"]) +
        ["-i", cap, "-i", music, "-filter_complex", graph, "-map", "[o]", "-ar", "44100", "-ac", "2",
         "-t", f"{total}", out])
    return out


if __name__ == "__main__":
    print(mix(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else ""))
