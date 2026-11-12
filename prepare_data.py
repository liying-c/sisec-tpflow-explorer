"""
把 SiSEC 2018 MUS 評測結果（github.com/sigsep/sigsep-mus-2018）彙整成網頁用的精簡 CSV。
只用 Python 標準函式庫。

用法:
    python3 -I prepare_data.py /path/to/sigsep-mus-2018

輸出 (public/data/):
    systems.csv            每個系統的屬性：類別、是否 blind、是否用額外訓練資料、作者、機構、程式連結
    tracks.csv             50 首 MUSDB18 測試曲：id、歌手、曲名、長度（秒）
    scores_track.csv       曲目層級分數：system, track, target, SDR, SIR, SAR, ISR（各為逐秒分數的中位數）
    frames/<track_id>.csv  逐秒分數：system, target, time, SDR, SIR, SAR, ISR（選到某首歌時才載入）

評測規則（museval / SiSEC 2018）：每個指標先對一首歌的所有秒數取中位數，
系統排名再對 50 首歌取中位數。靜音秒數的指標為 NaN 或 ±inf，取中位數時忽略。
"""
import csv
import json
import math
import re
import statistics
import sys
from pathlib import Path

ORACLES = {"IBM1", "IBM2", "IRM1", "IRM2", "MWF", "MIX"}
METRICS = ["SDR", "SIR", "SAR", "ISR"]
TARGETS = ["vocals", "drums", "bass", "other", "accompaniment"]
OUT = Path(__file__).resolve().parent / "public" / "data"


def slug(name):
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


def parse_description(path):
    """從 description.md 抓結構化欄位。前三行依範本是：# 短名、作者、機構。"""
    raw = path.read_bytes()
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:          # MDL1 / MDLT 是 latin-1 存檔
        text = raw.decode("latin-1")
    lines = [re.sub(r"<!--.*?-->", "", l).strip() for l in text.splitlines()]
    lines = [l for l in lines if l]
    authors = lines[1] if len(lines) > 1 and not lines[1].startswith("#") else ""
    affiliation = lines[2] if len(lines) > 2 and not lines[2].startswith("#") and "@" not in lines[2] else ""
    # 機構可能有 ¹² 這種註腳符號，清掉
    affiliation = re.sub(r"[¹²³⁴⁵]|<br/?>", " ", affiliation)
    affiliation = re.sub(r"\s+", " ", affiliation).strip()
    authors = re.sub(r"[¹²³⁴⁵]", "", authors).strip()

    def field(key):
        m = re.search(rf"__{key}:__\s*([^\n]*)", text)
        return m.group(1).strip() if m else ""

    def yesno(v):
        v = v.lower()
        if v.startswith("yes"):
            return "yes"
        if v.startswith("no"):
            return "no"
        return v or "?"

    code = field("Code")
    code = code if code.startswith("http") and "github.com/my/repo" not in code else ""   # RPCA 填的是範本佔位字串
    return {
        "authors": authors,
        "affiliation": affiliation,
        "is_blind": yesno(field("is_blind")),
        "extra_data": yesno(field("additional_training_data")),
        "code": code,
    }


def finite(v):
    return v is not None and isinstance(v, (int, float)) and math.isfinite(v)


def median_or_nan(values):
    vals = [v for v in values if finite(v)]
    return statistics.median(vals) if vals else float("nan")


def fmt(v, nd=3):
    return "" if (v is None or (isinstance(v, float) and math.isnan(v))) else f"{v:.{nd}f}"


def main(root):
    sub_dir = Path(root) / "submissions"
    systems = sorted(p.name for p in sub_dir.iterdir() if p.is_dir())
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "frames").mkdir(exist_ok=True)

    # ---- systems.csv ----
    with open(OUT / "systems.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["system", "category", "is_blind", "extra_data", "authors", "affiliation", "code"])
        for s in systems:
            d = parse_description(sub_dir / s / "description.md")
            if s in ORACLES:
                cat = "oracle"
            elif d["is_blind"] == "yes":
                cat = "blind"
            elif d["extra_data"] == "yes":
                cat = "supervised+extra"
            else:
                cat = "supervised"
            w.writerow([s, cat, d["is_blind"], d["extra_data"], d["authors"], d["affiliation"], d["code"]])

    # ---- 讀所有 JSON ----
    # scores[track][system][target] = { metric: [per-second values] }
    scores = {}
    for s in systems:
        for jp in sorted((sub_dir / s / "test").glob("*.json")):
            track = jp.stem
            data = json.loads(jp.read_text(encoding="utf-8"))
            for t in data["targets"]:
                frames = sorted(t["frames"], key=lambda fr: fr["time"])
                scores.setdefault(track, {}).setdefault(s, {})[t["name"]] = frames

    tracks = sorted(scores)
    track_id = {t: slug(t) for t in tracks}

    # ---- tracks.csv ----
    with open(OUT / "tracks.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["track_id", "artist", "title", "duration_s"])
        for t in tracks:
            artist, _, title = t.partition(" - ")
            any_sys = next(iter(scores[t].values()))
            any_target = next(iter(any_sys.values()))
            w.writerow([track_id[t], artist, title, len(any_target)])

    # ---- scores_track.csv（逐秒中位數）----
    n_rows = 0
    with open(OUT / "scores_track.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["system", "track_id", "target"] + METRICS)
        for t in tracks:
            for s in systems:
                for target in TARGETS:
                    frames = scores[t].get(s, {}).get(target)
                    if not frames:
                        continue
                    row = [s, track_id[t], target]
                    for m in METRICS:
                        row.append(fmt(median_or_nan([fr["metrics"].get(m) for fr in frames])))
                    w.writerow(row)
                    n_rows += 1

    # ---- frames/<track_id>.csv ----
    for t in tracks:
        with open(OUT / "frames" / f"{track_id[t]}.csv", "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["system", "target", "time"] + METRICS)
            for s in systems:
                for target in TARGETS:
                    for fr in scores[t].get(s, {}).get(target, []):
                        w.writerow([s, target, int(fr["time"])] +
                                   [fmt(fr["metrics"].get(m) if finite(fr["metrics"].get(m)) else None, 2) for m in METRICS])

    print(f"systems: {len(systems)}  tracks: {len(tracks)}  scores_track rows: {n_rows}")
    # 官方排名用的摘要：每個系統在 vocals 的 SDR（50 首歌中位數）
    import collections
    agg = collections.defaultdict(list)
    with open(OUT / "scores_track.csv", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            if r["target"] == "vocals" and r["SDR"]:
                agg[r["system"]].append(float(r["SDR"]))
    ranking = sorted(((statistics.median(v), s) for s, v in agg.items()), reverse=True)
    print("vocals SDR (median over tracks):")
    for med, s in ranking[:10]:
        print(f"  {s:5s} {med:6.2f} dB")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    main(sys.argv[1])
