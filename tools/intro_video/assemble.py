"""Yozib olingan kadrlardan tanishtiruv videosini yig'adi.

    python assemble.py <yozuv papkasi> <chiqish.mp4> [--audio <papka>] [--no-subs]

Har sahna (marks.json) alohida bo'lak. Ovoz berilsa (`<papka>/01.mp3` ... yoki .wav/.m4a/.ogg), har bo'lak
o'sha sahna ovozining uzunligiga moslanadi: ovoz uzun bo'lsa — sahnaning oxirgi kadri ushlab turiladi,
qisqa bo'lsa — sahna biroz tezlashtiriladi (odatda ko'pi bilan 1.35 marta, kutish sahnalarida ko'proq), qolgani jimlik. Ovoz bo'lmasa —
uzunlik matndan taxmin qilinadi (o'zbekcha nutq ~2.3 so'z/soniya).
"""
import json, os, re, shutil, subprocess, sys, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
FPS = 30
PAD = 0.45            # ovozdan keyin qoladigan sukut (soniya)
MAX_SPEED = 1.35
# Kutish yoki yozish ko'p bo'lgan sahnalar ko'proq tezlashtirilishi mumkin (animatsiya baribir ravon qoladi).
SPEED_CAP = {"05": 2.4, "12": 1.9, "07": 2.0, "08": 2.1, "09": 1.6, "03": 1.5}


def run(cmd):
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        raise SystemExit("ffmpeg xatosi:\n" + r.stderr[-2000:])
    return r


def duration(path):
    r = run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=nw=1:nk=1", path])
    return float(r.stdout.strip())


def audio_of(folder, sid):
    if not folder:
        return None
    for ext in (".mp3", ".wav", ".m4a", ".ogg", ".aac", ".opus", ".webm"):
        p = os.path.join(folder, sid + ext)
        if os.path.exists(p):
            return p
    return None


def ass_time(t):
    h, rem = divmod(max(0.0, t), 3600)
    m, s = divmod(rem, 60)
    return f"{int(h)}:{int(m):02d}:{s:05.2f}"


def chunks(text, limit):
    """Subtitr bo'laklari: gaplarga, uzun gap — vergul bo'yicha."""
    parts = re.split(r"(?<=[.!?])\s+", text.strip())
    out = []
    for p in parts:
        while len(p) > limit:
            cut = p.rfind(",", 0, limit)
            cut = cut if cut > limit * 0.4 else p.rfind(" ", 0, limit)
            out.append(p[:cut + 1].strip()); p = p[cut + 1:].strip()
        if p:
            out.append(p)
    return out


def main():
    args = sys.argv[1:]
    rec, out = os.path.abspath(args[0]), os.path.abspath(args[1])
    os.makedirs(os.path.dirname(out), exist_ok=True)
    audio_dir = args[args.index("--audio") + 1] if "--audio" in args else None
    subs = "--no-subs" not in args
    frames = json.load(open(os.path.join(rec, "frames.json")))
    marks = json.load(open(os.path.join(rec, "marks.json")))
    scenes = {s["id"]: s for s in json.load(open(os.path.join(HERE, "scenes.json"), encoding="utf-8"))}
    frames.sort(key=lambda f: f["t"])
    first = open(os.path.join(rec, "frames", frames[0]["file"]), "rb").read()
    size = run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height", "-of", "csv=p=0",
                os.path.join(rec, "frames", frames[0]["file"])]).stdout.strip().split(",")
    W, H = int(size[0]), int(size[1])
    W, H = W - W % 2, H - H % 2
    vertical = H > W
    work = tempfile.mkdtemp(prefix="asm_")
    clips, timeline, t0 = [], [], 0.0
    report = []
    for i, m in enumerate(marks[:-1]):
        sid, start, end = m["id"], m["t"], marks[i + 1]["t"]
        inside = [f for f in frames if start <= f["t"] < end]
        before = [f for f in frames if f["t"] < start]
        if before:
            inside = [{"t": start, "file": before[-1]["file"]}] + inside
        natural = end - start
        voice = audio_of(audio_dir, sid)
        if voice:
            target = duration(voice) + PAD
        else:
            words = len(scenes[sid]["text"].split())
            target = words / 2.3 + 0.8
        speed = 1.0
        if target < natural:
            speed = min(SPEED_CAP.get(sid, MAX_SPEED), natural / target)
        lst = os.path.join(work, f"{sid}.txt")
        with open(lst, "w") as fh:
            for k, f in enumerate(inside):
                nxt = inside[k + 1]["t"] if k + 1 < len(inside) else end
                d = max(1.0 / FPS, (nxt - f["t"]) / speed)
                fh.write(f"file '{os.path.join(rec, 'frames', f['file'])}'\nduration {d:.4f}\n")
            span = natural / speed
            hold = max(0.0, target - span)
            if hold > 0:
                fh.write(f"file '{os.path.join(rec, 'frames', inside[-1]['file'])}'\nduration {hold:.4f}\n")
            fh.write(f"file '{os.path.join(rec, 'frames', inside[-1]['file'])}'\n")
        clip = os.path.join(work, f"{sid}.mp4")
        length = max(target, natural / speed)
        run(["ffmpeg", "-y", "-v", "error", "-f", "concat", "-safe", "0", "-i", lst, "-vf",
             f"scale={W}:{H}:flags=lanczos,fps={FPS},format=yuv420p", "-t", f"{length:.3f}",
             "-c:v", "libx264", "-preset", "medium", "-crf", "18", clip])
        real = duration(clip)
        clips.append(clip)
        timeline.append((sid, t0, real, voice))
        report.append(f"{sid} {scenes[sid]['name']:<22} ekranda {natural:5.1f}s → video {real:5.1f}s"
                      + (f"  (ovoz {duration(voice):.1f}s" + (f", tezlik ×{speed:.2f}" if speed > 1 else "") + ")" if voice else "  (taxminiy)"))
        t0 += real

    joined = os.path.join(work, "joined.mp4")
    with open(os.path.join(work, "all.txt"), "w") as fh:
        fh.writelines(f"file '{c}'\n" for c in clips)
    run(["ffmpeg", "-y", "-v", "error", "-f", "concat", "-safe", "0", "-i", os.path.join(work, "all.txt"), "-c", "copy", joined])

    # Subtitr (ASS) va SRT
    font = 54 if vertical else 40
    margin = 160 if vertical else 56
    limit = 34 if vertical else 70
    ass = [f"[Script Info]\nScriptType: v4.00+\nPlayResX: {W}\nPlayResY: {H}\nWrapStyle: 0\n",
           "[V4+ Styles]\nFormat: Name, Fontname, Fontsize, PrimaryColour, OutlineColour, BackColour, Bold, Italic, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV\n"
           f"Style: Sub,Liberation Sans,{font},&H00FFFFFF,&H00000000,&H9E141A26,1,0,3,14,0,2,{margin // 2},{margin // 2},{margin}\n",
           "[Events]\nFormat: Layer, Start, End, Style, Text\n"]
    srt, n = [], 1
    cues_all = {}
    if audio_dir and os.path.exists(os.path.join(audio_dir, "cues.json")):
        cues_all = json.load(open(os.path.join(audio_dir, "cues.json"), encoding="utf-8"))
    for sid, start, length, voice in timeline:
        if voice and sid in cues_all:
            # Ovozdagi haqiqiy pauzalar bo'yicha: bo'laklar gap oxirigacha (yoki satr to'lguncha) qo'shiladi.
            lines, cur = [], None
            for c in cues_all[sid]:
                if cur and len(cur["text"]) + 1 + len(c["text"]) > limit * 2:
                    lines.append(cur); cur = None
                cur = dict(c) if not cur else {**cur, "text": cur["text"] + " " + c["text"], "end": c["end"]}
                if c["brk"] in "SE":
                    lines.append(cur); cur = None
            if cur:
                lines.append(cur)
            for k, ln_ in enumerate(lines):
                a = start + ln_["start"]
                b = start + (lines[k + 1]["start"] if k + 1 < len(lines) else min(length - 0.05, ln_["end"] + 0.6))
                ass.append(f"Dialogue: 0,{ass_time(a)},{ass_time(b)},Sub,{ln_['text']}\n")
                srt.append(f"{n}\n{ass_time(a).replace('.', ',')}0 --> {ass_time(b).replace('.', ',')}0\n{ln_['text']}\n")
                n += 1
            continue
        parts = chunks(scenes[sid]["text"], limit * 2)
        total = sum(len(p) for p in parts) or 1
        speak = (duration(voice) if voice else length - 0.3)
        at = start + 0.15
        for p in parts:
            d = speak * len(p) / total
            a, b = at, min(start + length - 0.05, at + d)
            text = p.replace("\n", " ")
            ass.append(f"Dialogue: 0,{ass_time(a)},{ass_time(b)},Sub,{text}\n")
            srt.append(f"{n}\n{ass_time(a).replace('.', ',')}0 --> {ass_time(b).replace('.', ',')}0\n{text}\n")
            n += 1; at = b
    ass_path = os.path.join(work, "subs.ass")
    open(ass_path, "w", encoding="utf-8").write("".join(ass))
    open(os.path.splitext(out)[0] + ".srt", "w", encoding="utf-8").write("\n".join(srt))

    vf = [f"ass={ass_path}"] if subs else []
    cmd = ["ffmpeg", "-y", "-v", "error", "-i", joined]
    if audio_dir and any(v for *_, v in timeline):
        filt, labels = [], []
        for k, (sid, start, length, voice) in enumerate(timeline):
            if voice:
                cmd += ["-i", voice]
                idx = len([1 for *_, vv in timeline[:k + 1] if vv])
                filt.append(f"[{idx}:a]aresample=48000,apad,atrim=0:{length:.3f}[a{k}]")
            else:
                filt.append(f"anullsrc=r=48000:cl=stereo,atrim=0:{length:.3f}[a{k}]")
            labels.append(f"[a{k}]")
        filt.append("".join(labels) + f"concat=n={len(labels)}:v=0:a=1,loudnorm=I=-16:TP=-1.5,aresample=48000[aout]")
        cmd += ["-filter_complex", ";".join(filt) + (f";[0:v]{','.join(vf)}[vout]" if vf else ""),
                "-map", "[vout]" if vf else "0:v", "-map", "[aout]", "-c:a", "aac", "-b:a", "160k"]
    elif vf:
        cmd += ["-vf", ",".join(vf)]
    cmd += ["-c:v", "libx264", "-preset", "slow", "-crf", "20", "-pix_fmt", "yuv420p", "-movflags", "+faststart", out]
    run(cmd)
    shutil.rmtree(work, ignore_errors=True)
    print("\n".join(report))
    print(f"Jami: {duration(out):.1f} s → {out} ({os.path.getsize(out) / 1e6:.1f} MB)")


if __name__ == "__main__":
    main()
