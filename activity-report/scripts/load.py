"""Load activity data from many sources into one normalized table.

Supported inputs (a file or a folder):
  - Strava bulk export: activities.csv in English or Vietnamese (or the export folder)
  - Garmin Connect "Activities.csv"
  - Any CSV with a date column plus some of: type, distance, duration, heart rate, elevation, calories
  - GPX / TCX files (optionally .gz), and FIT files when `fitdecode` is installed

Normalized columns:
  start (local datetime), sport (canonical), name, km, minutes, hr (avg bpm), elev (m gain), kcal, temp (deg C)
"""
from __future__ import annotations

import gzip
import math
import os
import re
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta

import numpy as np
import pandas as pd

COLS = ["start", "sport", "name", "km", "minutes", "hr", "elev", "kcal", "temp"]

# --- sport normalisation -----------------------------------------------------

SPORT_WORDS = [
    ("run", ["run", "chạy", "jog", "trail run", "treadmill"]),
    ("ride", ["ride", "cycl", "bike", "đạp xe", "xe đạp", "biking"]),
    ("walk", ["walk", "đi bộ"]),
    ("hike", ["hike", "hiking", "leo núi", "đường dài"]),
    ("swim", ["swim", "bơi"]),
    ("badminton", ["badminton", "cầu lông"]),
    ("tennis", ["tennis", "quần vợt"]),
    ("pickleball", ["pickleball"]),
    ("football", ["football", "soccer", "bóng đá"]),
    ("yoga", ["yoga"]),
    ("strength", ["weight", "strength", "tạ", "gym", "crossfit"]),
    ("workout", ["workout", "tập luyện", "training", "hiit", "cardio", "elliptical"]),
]
# Sports named by the activity title even when logged as a generic workout
NAME_OVERRIDES = ["badminton", "tennis", "pickleball", "football", "yoga", "swim"]


def canon_sport(kind: str, name: str = "") -> str:
    kind_l, name_l = str(kind or "").lower(), str(name or "").lower()
    if any(w in kind_l for w in ["walk", "đi bộ"]) and any(w in kind_l for w in ["hike", "đường dài"]):
        return "hike"
    found = "other"
    for sport, words in SPORT_WORDS:
        if any(w in kind_l for w in words):
            found = sport
            break
    if found in ("workout", "other", "strength"):
        for sport, words in SPORT_WORDS:
            if sport in NAME_OVERRIDES and any(w in name_l for w in words):
                return sport
    return found


# --- generic helpers ---------------------------------------------------------

def to_minutes(v):
    """Seconds (number) or h:mm:ss / mm:ss text -> minutes."""
    if v is None or (isinstance(v, float) and math.isnan(v)):
        return np.nan
    if isinstance(v, (int, float, np.number)):
        return float(v) / 60
    s = str(v).strip()
    if not s or s in ("--", "nan"):
        return np.nan
    if ":" in s:
        parts = [float(p) for p in re.split(r"[:]", s.split(".")[0])]
        while len(parts) < 3:
            parts.insert(0, 0)
        h, m, sec = parts[-3:]
        return h * 60 + m + sec / 60
    try:
        return float(s.replace(",", "")) / 60
    except ValueError:
        return np.nan


def to_num(series: pd.Series) -> pd.Series:
    if series.dtype == object:
        series = series.astype(str).str.replace(",", "", regex=False).str.replace("--", "", regex=False)
    return pd.to_numeric(series, errors="coerce")


VI_DATE = re.compile(r"(\d+):(\d+):(\d+) (\d+) thg (\d+), (\d+)")


def parse_date(s):
    if s is None or (isinstance(s, float) and math.isnan(s)):
        return pd.NaT
    s = str(s).strip()
    m = VI_DATE.match(s)
    if m:
        h, mi, se, d, mo, y = map(int, m.groups())
        return pd.Timestamp(y, mo, d, h, mi, se)
    for fmt in ("%b %d, %Y, %I:%M:%S %p", "%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%d/%m/%Y %H:%M", "%Y-%m-%d"):
        try:
            return pd.Timestamp(datetime.strptime(s.replace("Z", ""), fmt))
        except ValueError:
            pass
    try:
        return pd.Timestamp(pd.to_datetime(s)).tz_localize(None)
    except (ValueError, TypeError):
        return pd.NaT


# --- CSV readers -------------------------------------------------------------

STRAVA_EN = dict(date="Activity Date", type="Activity Type", name="Activity Name", sec="Moving Time",
                 m="Distance.1", hr="Average Heart Rate", elev="Elevation Gain", kcal="Calories",
                 temp="Weather Temperature", elapsed="Elapsed Time")
STRAVA_VI = dict(date="Ngày hoạt động", type="Loại hoạt động", name="Tên hoạt động", sec="Thời gian di chuyển",
                 m="Quãng đường.1", hr="Nhịp tim trung bình", elev="Độ cao tăng", kcal="Lượng calo",
                 temp="Nhiệt độ ngoài trời", elapsed="Thời gian thực tế")


def _strava(raw: pd.DataFrame, c: dict, utc_offset: float) -> pd.DataFrame:
    g = lambda k: raw[c[k]] if c[k] in raw else pd.Series(np.nan, index=raw.index)
    sec = to_num(g("sec")).fillna(to_num(g("elapsed")))
    df = pd.DataFrame({
        "start": g("date").map(parse_date) + pd.Timedelta(hours=utc_offset),
        "kind": g("type"), "name": g("name"),
        "km": to_num(g("m")) / 1000, "minutes": sec / 60,
        "hr": to_num(g("hr")), "elev": to_num(g("elev")), "kcal": to_num(g("kcal")), "temp": to_num(g("temp")),
    })
    return df


GENERIC_KEYS = {
    "date": ["start_time", "start", "date", "activity date", "datetime", "time_start", "ngày"],
    "type": ["sport", "type", "activity type", "activity_type", "loại"],
    "name": ["name", "title", "activity name", "tên"],
    "km": ["distance_km", "km", "distance (km)", "distance"],
    "m": ["distance_m", "meters", "distance (m)"],
    "dur": ["moving_time", "duration", "time", "elapsed_time", "moving time", "elapsed time", "duration_min", "minutes"],
    "hr": ["avg_hr", "average heart rate", "avg hr", "heart_rate", "hr", "average_heartrate"],
    "elev": ["elevation_gain", "total ascent", "elev", "ascent", "total_elevation_gain"],
    "kcal": ["calories", "kcal"],
    "temp": ["temperature", "temp", "avg temperature"],
}


def _find(cols, keys):
    low = {c.lower().strip(): c for c in cols}
    for k in keys:
        if k in low:
            return low[k]
    for k in keys:
        for lc, c in low.items():
            if lc.startswith(k):
                return c
    return None


def _generic(raw: pd.DataFrame, utc_offset: float) -> pd.DataFrame:
    f = {k: _find(raw.columns, v) for k, v in GENERIC_KEYS.items()}
    if not f["date"]:
        raise ValueError("Could not find a date column. Columns: " + ", ".join(raw.columns))
    g = lambda k: raw[f[k]] if f[k] else pd.Series(np.nan, index=raw.index)
    km = to_num(g("km"))
    if f["m"]:
        km = to_num(g("m")) / 1000
    elif km.dropna().median() > 400:  # looks like metres
        km = km / 1000
    dur_col = f["dur"]
    if dur_col and ("min" in dur_col.lower()):
        minutes = to_num(g("dur"))
    else:
        minutes = g("dur").map(to_minutes)
    return pd.DataFrame({
        "start": g("date").map(parse_date) + pd.Timedelta(hours=utc_offset),
        "kind": g("type").fillna("other"), "name": g("name"),
        "km": km, "minutes": minutes, "hr": to_num(g("hr")), "elev": to_num(g("elev")),
        "kcal": to_num(g("kcal")), "temp": to_num(g("temp")),
    })


def read_csv(path: str, utc_offset: float) -> pd.DataFrame:
    raw = pd.read_csv(path)
    if STRAVA_VI["date"] in raw:
        return _strava(raw, STRAVA_VI, utc_offset)
    if STRAVA_EN["date"] in raw and "Distance.1" in raw:
        return _strava(raw, STRAVA_EN, utc_offset)
    return _generic(raw, utc_offset)


# --- track files -------------------------------------------------------------

def _hav(a, b):
    r = 6371.0088
    la1, lo1, la2, lo2 = map(math.radians, (a[0], a[1], b[0], b[1]))
    h = math.sin((la2 - la1) / 2) ** 2 + math.cos(la1) * math.cos(la2) * math.sin((lo2 - lo1) / 2) ** 2
    return 2 * r * math.asin(math.sqrt(h))


def _summarise(points, kind, name, utc_offset):
    """points: list of (time, lat, lon, ele, hr) with time as naive UTC datetime."""
    pts = [p for p in points if p[0] is not None]
    if len(pts) < 2:
        return None
    km = moving = gain = 0.0
    for a, b in zip(pts, pts[1:]):
        if None not in (a[1], b[1]):
            d = _hav(a[1:3], b[1:3])
            dt = (b[0] - a[0]).total_seconds()
            km += d
            if dt > 0 and d / dt * 3600 > 1.0:  # moving faster than 1 km/h
                moving += dt
        if a[3] is not None and b[3] is not None and b[3] > a[3]:
            gain += b[3] - a[3]
    hrs = [p[4] for p in pts if p[4]]
    total = (pts[-1][0] - pts[0][0]).total_seconds()
    return dict(start=pd.Timestamp(pts[0][0]) + pd.Timedelta(hours=utc_offset), kind=kind, name=name,
                km=km, minutes=(moving or total) / 60, hr=float(np.mean(hrs)) if hrs else np.nan,
                elev=gain, kcal=np.nan, temp=np.nan)


def _open(path):
    return gzip.open(path, "rb") if path.endswith(".gz") else open(path, "rb")


def _t(s):
    d = datetime.fromisoformat(s.strip().replace("Z", "+00:00"))
    return (d - d.utcoffset()).replace(tzinfo=None) if d.tzinfo else d


def _strip_ns(root):
    for el in root.iter():
        if isinstance(el.tag, str) and "}" in el.tag:
            el.tag = el.tag.split("}", 1)[1]
    return root


def read_gpx(path, utc_offset):
    root = _strip_ns(ET.parse(_open(path)).getroot())
    trk = root.find("trk")
    kind = (trk.findtext("type") if trk is not None else "") or ""
    name = (trk.findtext("name") if trk is not None else "") or os.path.basename(path)
    pts = []
    for p in root.iter("trkpt"):
        t = p.findtext("time")
        ele = p.findtext("ele")
        hr = None
        for el in p.iter():
            if el.tag in ("hr", "heartrate"):
                hr = float(el.text)
        pts.append((_t(t) if t else None, float(p.get("lat")), float(p.get("lon")),
                    float(ele) if ele else None, hr))
    return _summarise(pts, kind or name, name, utc_offset)


def read_tcx(path, utc_offset):
    root = _strip_ns(ET.parse(_open(path)).getroot())
    act = root.find(".//Activity")
    kind = act.get("Sport", "") if act is not None else ""
    pts = []
    for tp in root.iter("Trackpoint"):
        t = tp.findtext("Time")
        lat, lon = tp.findtext("Position/LatitudeDegrees"), tp.findtext("Position/LongitudeDegrees")
        ele, hr = tp.findtext("AltitudeMeters"), tp.findtext("HeartRateBpm/Value")
        pts.append((_t(t) if t else None, float(lat) if lat else None, float(lon) if lon else None,
                    float(ele) if ele else None, float(hr) if hr else None))
    return _summarise(pts, kind, os.path.basename(path), utc_offset)


def read_fit(path, utc_offset):
    try:
        import fitdecode
    except ImportError:
        return None
    sess = {}
    with fitdecode.FitReader(_open(path)) as fr:
        for frame in fr:
            if isinstance(frame, fitdecode.FitDataMessage) and frame.name == "session":
                sess = {f.name: f.value for f in frame.fields}
                break
    if not sess.get("start_time"):
        return None
    st = sess["start_time"]
    st = st.replace(tzinfo=None) - (st.utcoffset() or timedelta(0))
    sec = sess.get("total_timer_time") or sess.get("total_elapsed_time") or 0
    return dict(start=pd.Timestamp(st) + pd.Timedelta(hours=utc_offset), kind=str(sess.get("sport", "")),
                name=str(sess.get("sub_sport", "")) or os.path.basename(path),
                km=(sess.get("total_distance") or 0) / 1000, minutes=sec / 60,
                hr=sess.get("avg_heart_rate") or np.nan, elev=sess.get("total_ascent") or np.nan,
                kcal=sess.get("total_calories") or np.nan, temp=sess.get("avg_temperature") or np.nan)


TRACK_READERS = {".gpx": read_gpx, ".tcx": read_tcx, ".fit": read_fit}


def _track_kind(path):
    p = path.lower()[:-3] if path.lower().endswith(".gz") else path.lower()
    return os.path.splitext(p)[1]


# --- entry point -------------------------------------------------------------

def load(path: str, utc_offset: float = 0.0) -> pd.DataFrame:
    """Return the normalized activity table, newest last."""
    frames, rows = [], []
    if os.path.isdir(path):
        csv = None
        for cand in ("activities.csv", "Activities.csv"):
            if os.path.exists(os.path.join(path, cand)):
                csv = os.path.join(path, cand)
        if csv:  # a Strava/Garmin export: the CSV already summarises every file
            frames.append(read_csv(csv, utc_offset))
        else:
            for root, _, files in os.walk(path):
                for fn in files:
                    full = os.path.join(root, fn)
                    reader = TRACK_READERS.get(_track_kind(fn))
                    if reader:
                        try:
                            r = reader(full, utc_offset)
                        except Exception as e:  # a broken file should not stop the report
                            print(f"skip {fn}: {e}")
                            r = None
                        if r:
                            rows.append(r)
                    elif fn.lower().endswith(".csv"):
                        frames.append(read_csv(full, utc_offset))
    elif path.lower().endswith(".csv"):
        frames.append(read_csv(path, utc_offset))
    else:
        r = TRACK_READERS[_track_kind(path)](path, utc_offset)
        rows.append(r)
    if rows:
        frames.append(pd.DataFrame(rows))
    if not frames:
        raise ValueError(f"No activity data found in {path}")
    df = pd.concat(frames, ignore_index=True)
    df = df[df.start.notna()].copy()
    df["sport"] = [canon_sport(k, n) for k, n in zip(df.kind, df.name)]
    for c in ("km", "minutes", "hr", "elev", "kcal", "temp"):
        df[c] = pd.to_numeric(df[c], errors="coerce")
    df.loc[df.km <= 0, "km"] = np.nan
    df.loc[df.hr <= 0, "hr"] = np.nan
    df["name"] = df["name"].fillna("").astype(str)
    df = df[df.minutes.fillna(0) > 0]
    return df.sort_values("start").drop_duplicates(["start", "sport"]).reset_index(drop=True)[COLS]
