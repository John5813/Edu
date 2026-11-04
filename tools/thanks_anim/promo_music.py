"""Reklama videosi uchun musiqa (numpy bilan sintez): 120 BPM, bitta zarb = 0,5 soniya.

Voqealar tasvir bilan aynan zarbga tushadi (`promo.py` shu vaqtlardan foydalanadi):
  0,0  kirish: zarb + bas + yengil arpedjio (Paxmoq raqsi)
  0,5  smayl chiqishi — "boing"
  2,0–3,5  ko'tarilish (riser) — kamera uzoqlashadi
  3,5  zarba (impact): barcha personajlar ko'rinadi, to'liq ritm boshlanadi
  4,5 / 6,0 / 7,5 / 9,0  shablonlar — har biridan oldin "vush" va yoqimli urg'u
  10,0 yakuniy akkord + qo'ng'iroqcha — logotip; 13,2 gacha so'nadi

    python tools/thanks_anim/promo_music.py out.wav
"""
import sys
import wave

import numpy as np

SR = 44100
BPM = 120
BEAT = 60 / BPM
TOTAL = 13.2
IMPACT = 3.5
ARRIVALS = (4.5, 6.0, 7.5, 9.0)
END = 10.0
SMILEY = 0.5

rng = np.random.default_rng(7)


def midi(n):
    return 440.0 * 2 ** ((n - 69) / 12)


def _t(dur):
    return np.arange(int(dur * SR)) / SR


def _place(mix, sig, at, gain=1.0, pan=0.0):
    i = int(at * SR)
    if i >= mix.shape[0] or i + len(sig) <= 0:
        return
    end = min(i + len(sig), mix.shape[0])
    seg = sig[: end - i] * gain
    l, r = np.cos((pan + 1) * np.pi / 4), np.sin((pan + 1) * np.pi / 4)
    mix[i:end, 0] += seg * l
    mix[i:end, 1] += seg * r


def kick():
    t = _t(0.42)
    f = 45 + 110 * np.exp(-t * 38)
    ph = 2 * np.pi * np.cumsum(f) / SR
    return (np.sin(ph) * np.exp(-t * 9) + 0.25 * np.exp(-t * 300) * rng.standard_normal(len(t)))


def _hp(x):
    return np.concatenate([[0], np.diff(x)])


def snare():
    t = _t(0.3)
    noise = _hp(rng.standard_normal(len(t))) * np.exp(-t * 18)
    tone = np.sin(2 * np.pi * 190 * t) * np.exp(-t * 28)
    return 0.7 * noise + 0.5 * tone


def clap():
    t = _t(0.28)
    env = sum(np.exp(-np.clip(t - d, 0, None) * 45) * (t >= d) for d in (0, 0.012, 0.024)) * 0.5
    return _hp(_hp(rng.standard_normal(len(t)))) * env * 0.5


def hat(open_=False):
    t = _t(0.22 if open_ else 0.05)
    return _hp(_hp(rng.standard_normal(len(t)))) * np.exp(-t * (14 if open_ else 90)) * 0.25


def bass(freq, dur=0.45):
    t = _t(dur)
    env = np.minimum(t / 0.006, 1) * np.exp(-t * 4.5)
    return (np.sin(2 * np.pi * freq * t) + 0.35 * np.sin(4 * np.pi * freq * t) + 0.12 * np.sin(6 * np.pi * freq * t)) * env


def pluck(freq, dur=0.5, bright=1.0):
    t = _t(dur)
    sig = np.zeros_like(t)
    for h in range(1, 9):
        if freq * h > 9000:
            break
        sig += np.sin(2 * np.pi * freq * h * t + h) * (1 / h ** 1.2) * np.exp(-t * (6 + 5 * h / bright))
    return sig * np.minimum(t / 0.004, 1)


def pad(freqs, dur, attack=0.5):
    t = _t(dur)
    env = np.minimum(t / attack, 1) * np.minimum((dur - t) / 0.4, 1)
    sig = sum(np.sin(2 * np.pi * f * t) + 0.5 * np.sin(2 * np.pi * f * 1.004 * t) + 0.2 * np.sin(4 * np.pi * f * t)
              for f in freqs)
    return sig * env * 0.08


def bell(freq, dur=2.6):
    t = _t(dur)
    sig = np.zeros_like(t)
    for ratio, amp, dec in ((1, 1, 1.6), (2.76, 0.45, 2.6), (5.4, 0.25, 4.0), (8.93, 0.12, 5.5), (2.0, 0.5, 2.0)):
        sig += amp * np.sin(2 * np.pi * freq * ratio * t) * np.exp(-t * dec)
    return sig * np.minimum(t / 0.002, 1)


def boing(dur=0.42):
    t = _t(dur)
    f = 260 + 520 * np.sin(np.pi * np.minimum(t / dur, 1) * 0.5) ** 2 + 40 * np.sin(2 * np.pi * 22 * t)
    ph = 2 * np.pi * np.cumsum(f) / SR
    return (np.sin(ph) + 0.3 * np.sin(2 * ph)) * np.exp(-t * 7) * np.minimum(t / 0.004, 1)


def riser(dur):
    t = _t(dur)
    k = (t / dur) ** 2.2
    f = 280 + 3200 * (t / dur) ** 2
    chirp = np.sin(2 * np.pi * np.cumsum(f) / SR)
    noise = _hp(rng.standard_normal(len(t)))
    return (0.45 * chirp + 0.9 * noise) * k * np.minimum((dur - t) / 0.03 + 0.0, 1) * 0.4


def whoosh(dur=0.55):
    t = _t(dur)
    env = np.sin(np.pi * np.minimum(t / dur, 1)) ** 2
    n = rng.standard_normal(len(t))
    soft = np.convolve(n, np.ones(6) / 6, "same")
    return (soft * 1.2 + _hp(n) * 0.5) * env * 0.5


def crash(dur=1.8):
    t = _t(dur)
    return _hp(_hp(rng.standard_normal(len(t)))) * np.exp(-t * 2.4) * 0.5


def boom(dur=1.2):
    t = _t(dur)
    f = 70 * np.exp(-t * 1.2) + 28
    return np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t * 2.8)


def reverb(x, wet=0.2, tail=1.1):
    n = int(tail * SR)
    tt = np.arange(n) / SR
    ir = rng.standard_normal((n, 2)) * np.exp(-tt * 4.2)[:, None]
    ir = ir - np.concatenate([np.zeros((1, 2)), ir[:-1]]) * 0.5          # biroz yorqinroq
    size = x.shape[0] + n
    out = np.zeros((x.shape[0], 2))
    for c in range(2):
        out[:, c] = np.fft.irfft(np.fft.rfft(x[:, c], size) * np.fft.rfft(ir[:, c], size), size)[: x.shape[0]]
    return x * (1 - wet * 0.5) + out * wet * 0.012


CHORDS = {                       # ildiz (MIDI), uchtovush
    "C": (48, (0, 4, 7)), "G": (43, (0, 4, 7)), "Am": (45, (0, 3, 7)), "F": (41, (0, 4, 7)),
}
PROG = ["C", "G", "Am", "F", "C"]                # har bir takt (2 soniya): 0–10 s


def render() -> np.ndarray:
    mix = np.zeros((int(TOTAL * SR), 2))
    full = lambda t: t >= IMPACT                  # to'liq ritm
    duck = np.ones(mix.shape[0])
    k = kick()

    # zarb: butun 0–10 s davomida har zarbda; intro (0–2) da yumshoqroq
    for b in range(int(END / BEAT)):
        at = b * BEAT
        if 2.5 <= at < IMPACT:                    # ko'tarilishda zarb yo'q — bo'shliq
            continue
        _place(mix, k, at, 0.85 if at >= 2 or at >= IMPACT else 0.7)
        i = int(at * SR)
        duck[i:i + int(0.22 * SR)] *= np.linspace(0.45, 1, int(0.22 * SR))[: len(duck[i:i + int(0.22 * SR)])]
    # hat — sakkizlikning ikkinchi yarmida; ochiq — har ikkinchi zarbda
    for e in range(int(END / (BEAT / 2))):
        at = e * BEAT / 2
        if 2.0 <= at < IMPACT:
            continue
        if e % 2 == 1:
            _place(mix, hat(open_=(e % 4 == 3)), at, 0.7 if full(at) else 0.4, pan=0.25)
    # klap: 2 va 4 zarblarda (kirishdan keyin)
    for b in range(int(END / BEAT)):
        at = b * BEAT
        if b % 2 == 1 and at >= 1.0 and not (2.0 <= at < IMPACT):
            _place(mix, clap(), at, 0.8 if full(at) else 0.55)

    # bas va arpedjio — akkord bo'yicha
    for bar, name in enumerate(PROG):
        root, tri = CHORDS[name]
        t0 = bar * 2.0
        for e in range(8):                       # sakkizliklar
            at = t0 + e * BEAT / 2
            if 2.0 <= at < IMPACT:
                continue
            if e % 2 == 0:
                _place(mix, bass(midi(root + (12 if e in (4, 6) and bar % 2 else 0)), 0.4), at, 0.55)
            note = root + 24 + tri[(0, 1, 2, 1, 0, 2, 1, 2)[e] % 3] + (12 if e in (6, 7) else 0)
            _place(mix, pluck(midi(note), 0.45), at, 0.2 if not full(at) else 0.26,
                   pan=-0.4 if e % 2 == 0 else 0.4)
    # yetakchi ohang (to'liq ritm paytida): oddiy, esda qoladigan motiv
    motif = {  # takt: [(sakkizlik, MIDI), ...]
        1: [(0, 79), (1, 76), (2, 79), (4, 81), (6, 79)],
        2: [(0, 76), (1, 72), (2, 76), (3, 79), (4, 76), (6, 74)],
        3: [(0, 77), (1, 74), (2, 77), (4, 81), (5, 79), (6, 77)],
        4: [(0, 79), (1, 76), (2, 74), (3, 76), (4, 79), (6, 83)],
    }
    for bar, notes in motif.items():
        for e, n in notes:
            at = bar * 2.0 + e * BEAT / 2
            if at < IMPACT or at >= END:
                continue
            _place(mix, pluck(midi(n), 0.5, bright=1.6), at, 0.32, pan=0.1)
    # pad (to'liq qism)
    for bar, name in enumerate(PROG):
        at = bar * 2.0
        if at + 2.0 <= IMPACT or at >= END:
            continue
        root, tri = CHORDS[name]
        start = max(at, IMPACT)
        _place(mix, pad([midi(root + 24 + i) for i in tri], at + 2.0 - start + 0.3, 0.5), start, 0.9)

    # maxsus effektlar
    _place(mix, boing(), SMILEY, 0.55, pan=0.2)
    _place(mix, riser(IMPACT - 2.0), 2.0, 0.85)
    for j in range(6):                            # snayr rolli — tezlashadi
        at = 2.0 + 1.5 * (1 - (1 - j / 6) ** 1.6)
        _place(mix, snare(), at, 0.2 + 0.08 * j)
    for at in (IMPACT - BEAT / 2, IMPACT - BEAT / 4):
        _place(mix, snare(), at, 0.55)
    _place(mix, crash(), IMPACT, 0.75)
    _place(mix, boom(), IMPACT, 0.95)
    _place(mix, k, IMPACT, 1.0)
    for at in ARRIVALS:
        _place(mix, whoosh(0.5), at - 0.5, 0.75, pan=-0.2)
        _place(mix, snare(), at, 0.45)
        _place(mix, bell(midi(88), 0.9), at, 0.12, pan=0.3)
    # yakun: ta-da akkord, qo'ng'iroqcha va yengil arpedjio
    _place(mix, boom(1.0), END, 0.7)
    _place(mix, crash(1.6), END, 0.5)
    _place(mix, k, END, 0.9)
    for n, d in ((60, 0), (64, 0), (67, 0), (72, 0), (76, 0.09), (79, 0.18), (84, 0.27), (88, 0.36)):
        _place(mix, pluck(midi(n), 0.9, bright=1.2), END + d, 0.30, pan=(n % 5 - 2) / 4)
    _place(mix, pad([midi(60), midi(64), midi(67), midi(72)], 2.4, 0.04), END, 0.9)
    _place(mix, bell(midi(84), 2.4), END + 0.45, 0.25, pan=-0.2)
    _place(mix, bell(midi(91), 2.2), END + 0.6, 0.2, pan=0.25)

    mix *= duck[:, None] ** 0.8                  # kick tagida pad/arp biroz o'chadi
    # (kick o'zi duck dan keyin qo'shilmasligi uchun yuqorida allaqachon chaladi — yengil ta'sir)
    mix = reverb(mix, 0.55)
    # master: tovush chegarasi, boshi/oxiri silliq
    mix = np.tanh(mix * 1.15) / np.tanh(1.15)
    peak = np.abs(mix).max()
    mix *= 0.63 / peak                            # ≈ −4 dBFS: AAC dan keyin ham chegaradan oshmaydi
    fade_in = int(0.005 * SR)
    mix[:fade_in] *= np.linspace(0, 1, fade_in)[:, None]
    fade_out = int(0.9 * SR)
    mix[-fade_out:] *= np.linspace(1, 0, fade_out)[:, None] ** 1.5
    return mix


def write_wav(path, mix):
    pcm = (np.clip(mix, -1, 1) * 32767).astype("<i2")
    with wave.open(path, "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(pcm.tobytes())


if __name__ == "__main__":
    write_wav(sys.argv[1], render())
    print("tayyor:", sys.argv[1])
