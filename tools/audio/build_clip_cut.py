# -*- coding: utf-8 -*-
"""build_clip_cut.py — пересборка звука клипа из ОРИГИНАЛА + вырезание пауз.

Метод обобщённый на произвольный клип:

  1. Звук берётся из ОРИГИНАЛА (только чтение):
     highpass=80 -> afftdn=nr=8:nf=-50 (мягкое ШП, фон комнаты/машины сохраняется).
  2. Адаптивный подъём тихих слов: гейт по огибающей (40/10 мс), потолок +9 dB,
     сглаживание 150 мс, гейт от шумового пола +6 dB.
  3. Лимитер −1,5 dBFS.
  4. Поиск «дыр»: окна ниже (фон + MARGIN dB) длиной ≥ 0,8 с. Дыра, в которую
     по пословной расшифровке попадает слышимое слово, НЕ отбрасывается целиком,
     а УСЕКАЕТСЯ: из неё вычитаются интервалы слов с запасом WORD_GUARD, а
     оставшиеся свободные куски ≥ 0,8 с вырезаются. (Таймкоды ASR
     вероятностные: слово может стоять в 0,10 с от края дыры. Отбрасывать дыру
     целиком означало бы оставить мёртвый воздух.)
  5. Вырезание найденных интервалов ИЗ КАРТИНКИ И ЗВУКА одновременно.

ВАЖНО: у клипа на таймлайне видео и звук могут быть взяты с РАЗНЫХ кадров
источника. Эти in-point'ы сохраняются дословно; пересборка их не трогает.

    python build_clip_cut.py --src <папка с оригиналами> --jobs jobs.json
                             [--out <корень проекта>] [--fps 25]

jobs.json: {"<CLIP>": {"video": [video_in, video_out], "audio": [audio_in, audio_out]}}
Все окна — в кадрах ИСХОДНИКА.
"""
import argparse
import json
import os
import subprocess
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import env_paths  # noqa: E402

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

SR = 48000
FPS = 25
LIMIT = 0.841                 # −1,5 dBFS
ENV_WIN, ENV_HOP = 0.040, 0.010
SMOOTH = 0.150
MAX_GAIN = 9.0                # потолок подъёма, дБ
FLOOR_MARGIN = 6.0            # гейт: на 6 dB выше шумового пола — поднимаем
TARGET_PCT = 75.0             # целевой уровень речи = 75-й перцентиль огибающей
GAP_MIN = 0.8                 # минимальная длина «дыры», с
GAP_MARGIN = 8.0              # «дыра» = ниже (фон + GAP_MARGIN) dB
WORD_GUARD = 0.12             # запас вокруг слова, с (чтобы не срезать слог)

FF = env_paths.ffmpeg() or "ffmpeg"

# заполняется из --jobs: clip -> (video_in, video_out, audio_in, audio_out)
JOBS = {}
MODELS = ""
PROC = ""
FIXED = ""
TMP = ""
ORIG_DIR = ""


def run(cmd, cwd=None, timeout=7200, input_data=None):
    return subprocess.run(cmd, cwd=cwd, input=input_data, stdout=subprocess.PIPE,
                          stderr=subprocess.STDOUT, timeout=timeout)


def dec(path, ac=2, rate=SR, af=None):
    cmd = [FF, "-v", "error", "-i", path]
    if af:
        cmd += ["-af", af]
    cmd += ["-ac", str(ac), "-ar", str(rate), "-f", "f32le", "-acodec", "pcm_f32le", "-"]
    p = run(cmd)
    if p.returncode != 0:
        raise RuntimeError(p.stdout.decode("utf-8", "replace")[-500:])
    a = np.frombuffer(p.stdout, dtype=np.float32).astype(np.float64)
    if a.size == 0:
        raise RuntimeError("пустое аудио: " + path)
    if ac == 2:
        return a.reshape(-1, 2)
    return a


def db(x):
    return -999.0 if x <= 0 else 20.0 * float(np.log10(max(x, 1e-12)))


def envelope_db(a):
    if a.ndim == 2:
        a = a.mean(axis=1)
    w, hop = int(ENV_WIN * SR), int(ENV_HOP * SR)
    n = max(1, (len(a) - w) // hop)
    csum = np.concatenate(([0.0], np.cumsum(a ** 2)))
    idx = np.arange(n) * hop
    rms = np.sqrt((csum[idx + w] - csum[idx]) / w)
    return 20.0 * np.log10(np.maximum(rms, 1e-12)), hop


def smooth_gain(g, hop, n):
    k = max(1, int(SMOOTH / ENV_HOP))
    pad = np.pad(g, (k // 2, k - k // 2), mode="edge")
    return np.convolve(pad, np.ones(k) / k, mode="same")[k // 2: k // 2 + n]


def write_wav(path, a):
    if a.ndim == 1:
        a = a[:, None]
    inter = np.empty(a.shape[0] * a.shape[1], dtype=np.float32)
    inter[0::2] = a[:, 0]
    if a.shape[1] > 1:
        inter[1::2] = a[:, 1]
    cmd = [FF, "-v", "error", "-y", "-f", "f32le", "-ar", str(SR),
           "-ac", str(a.shape[1]), "-i", "-", "-c:a", "pcm_s24le", path]
    r = run(cmd, input_data=inter.tobytes())
    if r.returncode != 0:
        raise RuntimeError(r.stdout.decode("utf-8", "replace")[-400:])


def find_gaps(env, lo, hi, margin):
    """Дыры в окне кадров [lo,hi) по уровню «фон + margin»."""
    floor = float(np.percentile(env, 20))
    thr = floor + margin
    idx0, idx1 = int(lo / FPS / ENV_HOP), int(hi / FPS / ENV_HOP)
    idx1 = min(idx1, len(env))
    mask = env[idx0:idx1] < thr
    out = []
    i = 0
    while i < len(mask):
        if mask[i]:
            j = i
            while j < len(mask) and mask[j]:
                j += 1
            if (j - i) * ENV_HOP >= GAP_MIN:
                out.append((int((idx0 + i) * ENV_HOP * FPS),
                            int((idx0 + j) * ENV_HOP * FPS)))
            i = j
        else:
            i += 1
    return out, floor, thr


def asr_words(path, model_name="small"):
    """Пословная расшифровка: список (t0, t1, rms_dbfs) в секундах исходника."""
    from faster_whisper import WhisperModel
    a16 = dec(path, ac=1, rate=16000)
    a48 = dec(path, ac=1, rate=48000)
    model = WhisperModel(model_name, device="cpu", compute_type="int8", download_root=MODELS)
    segs, _ = model.transcribe(a16, language="ru", vad_filter=False,
                               condition_on_previous_text=False, beam_size=5,
                               word_timestamps=True)
    words = []
    for s in segs:
        for w in (s.words or []):
            i0, i1 = int(w.start * SR), int(w.end * SR)
            seg = a48[i0:i1]
            r = db(float(np.sqrt((seg ** 2).mean()))) if seg.size else -999.0
            words.append({"w": w.word.strip(), "t0": round(w.start, 2),
                          "t1": round(w.end, 2), "rms": round(r, 2)})
    return words


def build(clip, project_root, asr_model="small"):
    print("\n" + "=" * 70)
    print("КЛИП %s" % clip)
    print("=" * 70)
    job = JOBS[clip]
    vin, vout = job["video"]
    ain, aout = job["audio"]
    orig = os.path.join(ORIG_DIR, clip + ".MP4")
    if not os.path.exists(orig):
        print("нет оригинала:", orig)
        return None

    # ---------- 1. базовая обработка из оригинала ----------
    base_wav = os.path.join(TMP, "%s_base.wav" % clip)
    r = run([FF, "-v", "error", "-y", "-i", orig, "-vn",
             "-af", "highpass=f=80,afftdn=nr=8:nf=-50", "-c:a", "pcm_s24le",
             base_wav], cwd=MODELS)
    if r.returncode != 0:
        print("базовая обработка не удалась:", r.stdout.decode("utf-8", "replace")[-400:])
        return None
    a = dec(base_wav, ac=2)
    print("база: %.2f с" % (len(a) / SR))

    # ---------- 2. адаптивный подъём тихих слов ----------
    env, hop = envelope_db(a)
    floor = float(np.percentile(env, 10))
    speech = env[env > floor + FLOOR_MARGIN]
    target = float(np.percentile(speech, TARGET_PCT)) if speech.size else -20.0
    print("шумовой пол %.2f dBFS, цель речи %.2f dBFS" % (floor, target))

    gain = np.clip(target - env, 0.0, MAX_GAIN)
    gain[env <= floor + FLOOR_MARGIN] = 0.0
    g_s = smooth_gain(gain, hop, len(env))
    g_full = np.interp(np.arange(len(a)), np.arange(len(env)) * hop, 10 ** (g_s / 20.0))
    boosted = a * g_full[:, None]

    lim_wav = os.path.join(TMP, "%s_lim.wav" % clip)
    write_wav(os.path.join(TMP, "%s_boost.wav" % clip), boosted)
    r = run([FF, "-v", "error", "-y", "-i", os.path.join(TMP, "%s_boost.wav" % clip),
             "-af", "alimiter=limit=%.4f:level=disabled" % LIMIT, "-c:a", "pcm_s24le",
             lim_wav])
    if r.returncode != 0:
        print("лимитер не удался:", r.stdout.decode("utf-8", "replace")[-300:])
        return None
    final = dec(lim_wav, ac=2)
    env2, _ = envelope_db(final)
    print("после обработки: пол %.2f dBFS, медиана %.2f dBFS"
          % (float(np.percentile(env2, 10)), float(np.median(env2))))

    # ---------- 3. поиск дыр (свип по порогу) ----------
    print("\n-- свип порога (дыры в окне звука %d-%d кадров) --" % (ain, aout))
    sweep = []
    for margin in (4, 6, 8, 10, 12):
        gs, fl, thr = find_gaps(env2, ain, aout, margin)
        tot = sum((b - a) / FPS for a, b in gs)
        sweep.append({"margin": margin, "n": len(gs), "total_s": round(tot, 2),
                      "threshold_dbfs": round(thr, 2)})
        print("   порог фон+%2d dB (%.2f dBFS): %2d дыр, всего %6.2f с"
              % (margin, thr, len(gs), tot))

    gs, fl, thr = find_gaps(env2, ain, aout, GAP_MARGIN)
    print("\n-- дыры при пороге фон+%.0f dB --" % GAP_MARGIN)
    for a0, b0 in gs:
        print("   кадры %5d-%5d  (%6.2f-%6.2f с, %5.2f с)"
              % (a0, b0, a0 / FPS, b0 / FPS, (b0 - a0) / FPS))

    # ---------- 4. проверка по расшифровке + усечение дыр ----------
    print("\n-- пословная расшифровка (проверка, что в дырах нет слов) --")
    words = asr_words(orig, asr_model)
    json.dump(words, open(os.path.join(project_root, "audio", "%s_words.json" % clip),
                          "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    wfloor = float(np.percentile(env2, 20))
    audible = [w for w in words if w["rms"] > wfloor + 10.0]

    def merge_iv(ivs):
        out = []
        for x, y in sorted(ivs):
            if out and x <= out[-1][1]:
                out[-1][1] = max(out[-1][1], y)
            else:
                out.append([x, y])
        return [(x, y) for x, y in out]

    keep_gaps = []       # финальные интервалы вырезания (кадры)
    trimmed = []         # дыры, усечённые из-за слов
    full_cut = []        # дыры, вырезанные целиком
    for a0, b0 in gs:
        t0, t1 = a0 / FPS, b0 / FPS
        hits = [w for w in audible
                if w["t1"] > t0 - WORD_GUARD and w["t0"] < t1 + WORD_GUARD]
        blocked = []
        for w in hits:
            x = max(t0, w["t0"] - WORD_GUARD)
            y = min(t1, w["t1"] + WORD_GUARD)
            if y > x:
                blocked.append((x, y))
        free, cur = [], t0
        for x, y in merge_iv(blocked):
            if x > cur:
                free.append((cur, x))
            cur = max(cur, y)
        if cur < t1:
            free.append((cur, t1))
        good = [(x, y) for x, y in free if y - x >= GAP_MIN]
        if good:
            for x, y in good:
                keep_gaps.append((int(round(x * FPS)), int(round(y * FPS))))
                print("   ВЫРЕЗ кадры %d-%d (%.2f-%.2f с, %.2f с)  [дыра %d-%d усечена]"
                      % (int(round(x * FPS)), int(round(y * FPS)), x, y, y - x, a0, b0))
            if len(good) < len(free):
                trimmed.append({"from": a0, "to": b0,
                                "words": [w["w"] for w in hits][:8],
                                "free": [[round(x, 3), round(y, 3)] for x, y in free]})
        else:
            trimmed.append({"from": a0, "to": b0,
                            "words": [w["w"] for w in hits][:8],
                            "free": [[round(x, 3), round(y, 3)] for x, y in free]})
            print("   ПРОПУСК кадры %d-%d: задеты слова %s (свободного куска ≥ %.1f с нет)"
                  % (a0, b0, [w["w"] for w in hits][:6], GAP_MIN))
        if not hits:
            full_cut.append({"from": a0, "to": b0})
    keep_gaps = merge_iv([(float(a), float(b)) for a, b in keep_gaps])
    keep_gaps = [(int(round(a)), int(round(b))) for a, b in keep_gaps]
    total = sum((b - a) / FPS for a, b in keep_gaps)
    print("   итог: вырезать %d интервалов, всего %.2f с (усечено дыр: %d, отброшено: %d)"
          % (len(keep_gaps), total, len(trimmed), len(full_cut)))

    # ---------- 5. сборка: видео и звук режутся одинаково ----------
    # ВАЖНО: видео и звук могут иметь РАЗНЫЕ окна источника. Сегменты строятся
    # независимо для каждого окна, пересечением с непрерывными кусками между
    # вырезами. (Ошибка: раньше aparts строился из vsegs — в файл попадал лишний
    #  звук, и ASR слышал реплику, которую заказчик вырезал.)
    def segments(lo, hi):
        segs = []
        cur = lo
        for g0, g1 in sorted(keep_gaps):
            if g0 > cur:
                segs.append((cur, min(g0, hi)))
            cur = max(cur, g1)
            if cur >= hi:
                break
        if cur < hi:
            segs.append((cur, hi))
        return [(a, b) for a, b in segs if b > a]

    vsegs = segments(vin, vout)
    asegs = segments(ain, aout)
    print("\n-- отрезки --")
    print("   видео: %d отрезков, %d кадров (окно %d-%d)"
          % (len(vsegs), sum(b - a for a, b in vsegs), vin, vout))
    print("   звук : %d отрезков, %d кадров (окно %d-%d)"
          % (len(asegs), sum(b - a for a, b in asegs), ain, aout))
    if len(vsegs) != len(asegs):
        print("   ВНИМАНИЕ: число отрезков видео и звука различается (%d/%d)"
              % (len(vsegs), len(asegs)))

    vparts, aparts = [], []
    for i, (a0, b0) in enumerate(vsegs):
        vparts.append("[0:v]trim=start_frame=%d:end_frame=%d,setpts=PTS-STARTPTS[v%d]"
                      % (a0, b0, i))
    for i, (a0, b0) in enumerate(asegs):
        aparts.append("[1:a]atrim=start_sample=%d:end_sample=%d,asetpts=PTS-STARTPTS[a%d]"
                      % (a0 * SR // FPS, b0 * SR // FPS, i))
    vconcat = "".join("[v%d]" % i for i in range(len(vsegs)))
    aconcat = "".join("[a%d]" % i for i in range(len(asegs)))
    fc = ";".join(vparts) + ";" + vconcat + \
         "concat=n=%d:v=1:a=0[v]" % len(vsegs) + ";" + \
         ";".join(aparts) + ";" + aconcat + \
         "concat=n=%d:v=0:a=1[a]" % len(asegs)

    out = os.path.join(FIXED, "%s_cut.mp4" % clip)
    r = run([FF, "-v", "error", "-y", "-i", orig, "-i", lim_wav, "-filter_complex", fc,
             "-map", "[v]", "-map", "[a]", "-c:v", "libx264", "-preset", "medium",
             "-crf", "17", "-pix_fmt", "yuv420p", "-c:a", "pcm_s16be", "-ar", str(SR),
             out], timeout=7200)
    if r.returncode != 0:
        print("сборка не удалась:", r.stdout.decode("utf-8", "replace")[-600:])
        return None

    chk = dec(out, ac=2)
    peak = float(np.abs(chk).max())
    clipn = int((np.abs(chk) >= 0.999).sum())
    e3, _ = envelope_db(chk)
    print("\n-- итоговый файл --")
    print("   %s" % out)
    print("   длительность %.3f с (видео %d кадров)" % (len(chk) / SR,
                                                       sum(b - a for a, b in vsegs)))
    print("   пик %.2f dBFS, клиппинг %.4f%% (%d)" % (db(peak), 100.0 * clipn / chk.size, clipn))
    print("   шумовой пол после: %.2f dBFS" % float(np.percentile(e3, 10)))

    return {
        "clip": clip, "source": orig,
        "video_in": vin, "video_out": vout, "audio_in": ain, "audio_out": aout,
        "chain": "highpass=80,afftdn=nr=8:nf=-50 -> adaptive lift (max +9 dB) -> alimiter -1.5 dBFS",
        "floor_dbfs": round(fl, 2), "target_dbfs": round(target, 2),
        "gap_margin_db": GAP_MARGIN, "gap_threshold_dbfs": round(thr, 2),
        "sweep": sweep,
        "gaps": [{"from_frame": a0, "to_frame": b0, "from_s": round(a0 / FPS, 3),
                  "to_s": round(b0 / FPS, 3), "dur_s": round((b0 - a0) / FPS, 2)}
                 for a0, b0 in keep_gaps],
        "trimmed_gaps": trimmed,
        "full_cut_gaps": full_cut,
        "gap_total_s": round(total, 2),
        "video_segments": vsegs, "audio_segments": asegs,
        "out": out,
        "out_duration_s": round(len(chk) / SR, 3),
        "out_video_frames": sum(b - a for a, b in vsegs),
        "out_audio_frames": sum(b - a for a, b in asegs),
        "peak_dbfs": round(db(peak), 2), "clip_samples": clipn,
    }


def main(argv=None):
    global JOBS, MODELS, PROC, FIXED, TMP, ORIG_DIR, FPS

    p = argparse.ArgumentParser(
        prog="build_clip_cut.py",
        description="пересборка звука клипа из оригинала с вырезанием пауз")
    p.add_argument("--src", default="", help="папка с оригиналами (только чтение)")
    p.add_argument("--jobs", required=True,
                   help="JSON с окнами: {\"<CLIP>\": {\"video\": [in,out], \"audio\": [in,out]}}")
    p.add_argument("--out", default="", help="корень проекта для результатов")
    p.add_argument("--fps", type=float, default=25.0, help="fps исходника")
    p.add_argument("--models", default="", help="папка с моделями (ASR/Whisper)")
    p.add_argument("--asr-model", default="small", help="модель Whisper для пословной расшифровки")
    a = p.parse_args(argv)

    FPS = a.fps
    project = env_paths.project_root()
    root = os.path.abspath(a.out) if a.out else str(project)
    src = os.path.abspath(a.src) if a.src else str(env_paths.src_root() or "")
    if not src or not os.path.isdir(src):
        p.error("нет папки с оригиналами (укажи --src)")

    with open(os.path.abspath(a.jobs), encoding="utf-8") as f:
        raw_jobs = json.load(f)
    JOBS = {}
    for clip, spec in raw_jobs.items():
        JOBS[clip] = {"video": tuple(spec["video"]), "audio": tuple(spec["audio"])}

    MODELS = os.path.abspath(a.models) if a.models else os.path.join(root, "audio", "models")
    PROC = os.path.join(root, "audio", "proc")
    FIXED = os.path.join(root, "audio", "proc_mux_fixed")
    TMP = os.path.join(root, "audio", "_tmp")
    ORIG_DIR = src

    os.makedirs(TMP, exist_ok=True)
    os.makedirs(FIXED, exist_ok=True)
    os.makedirs(os.path.join(root, "audio"), exist_ok=True)

    rep = {}
    for clip in JOBS:
        rec = build(clip, root, a.asr_model)
        if rec:
            rep[clip] = rec
    out = os.path.join(root, "audio", "cut_plan.json")
    with open(out, "w", encoding="utf-8") as f:
        json.dump(rep, f, ensure_ascii=False, indent=1)
    print("\nотчёт: %s" % out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
