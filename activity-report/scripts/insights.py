"""Find the insights a normal chart hides.

Each finder returns None when the data cannot support it, or a dict:
  id, score (higher = more surprising), title, headline, detail, chart (spec for charts.py)
"""
from __future__ import annotations

import numpy as np
import pandas as pd

RIEGEL = 1.06
DAYS = {"vi": ["T2", "T3", "T4", "T5", "T6", "T7", "CN"], "en": ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]}
SPORT_NAMES = {
    "vi": dict(run="Chạy bộ", ride="Đạp xe", walk="Đi bộ", hike="Leo núi", swim="Bơi", badminton="Cầu lông",
               tennis="Tennis", pickleball="Pickleball", football="Bóng đá", yoga="Yoga", strength="Tập tạ",
               workout="Tập luyện", other="Khác"),
    "en": dict(run="Run", ride="Ride", walk="Walk", hike="Hike", swim="Swim", badminton="Badminton",
               tennis="Tennis", pickleball="Pickleball", football="Football", yoga="Yoga", strength="Strength",
               workout="Workout", other="Other"),
}


class Fmt:
    def __init__(self, lang):
        self.lang = lang

    def n(self, x, d=0):
        s = f"{x:,.{d}f}"
        return s.replace(",", "X").replace(".", ",").replace("X", ".") if self.lang == "vi" else s

    def pace(self, min_per_km):
        s = int(round(min_per_km * 60))
        return f"{s // 60}:{s % 60:02d}"

    def hms(self, minutes):
        s = int(round(minutes * 60))
        return f"{s // 3600}:{s % 3600 // 60:02d}:{s % 60:02d}" if s >= 3600 else f"{s // 60}:{s % 60:02d}"

    def t(self, vi, en):
        return vi if self.lang == "vi" else en

    def sport(self, s):
        return SPORT_NAMES[self.lang].get(s, s)


def runs(df, min_km=1.5):
    r = df[(df.sport == "run") & (df.km >= min_km)].copy()
    r["pace"] = r.minutes / r.km
    r = r[(r.pace > 2.5) & (r.pace < 12)]
    # 5K-equivalent time: removes the effect of distance on pace (Riegel)
    r["eq5k"] = r.minutes * (5 / r.km) ** RIEGEL
    return r


def endurance_type(df):
    """The distance sport with most sessions (run, ride, walk...), for the fitness insights."""
    for s in ("run", "ride", "walk", "hike"):
        if (df[df.sport == s].km.notna()).sum() >= 10:
            return s
    return None


# --- finders -----------------------------------------------------------------

def overview(df, f):
    end = df.start.max().normalize()
    start = end - pd.Timedelta(days=364)
    start -= pd.Timedelta(days=start.dayofweek)
    daily = df[df.start >= start].groupby(df.start.dt.normalize()).minutes.sum()
    days = pd.date_range(start, end)
    years = (df.start.max() - df.start.min()).days / 365.25
    return dict(
        id="overview", score=100,
        title=f.t("Tổng quan", "Overview"),
        headline=f.t(f"{f.n(len(df))} hoạt động trong {f.n(years, 1)} năm",
                     f"{f.n(len(df))} activities over {f.n(years, 1)} years"),
        detail=f.t("Mỗi ô là một ngày trong 12 tháng gần nhất, càng đậm càng nhiều phút vận động.",
                   "Each cell is a day of the last 12 months; darker means more minutes."),
        kpis=[(f.n(len(df)), f.t("hoạt động", "activities")),
              (f.n(df.minutes.sum() / 60), f.t("giờ", "hours")),
              (f.n(df.km.sum()), "km"),
              (f.n(df.kcal.sum()) if df.kcal.notna().any() else "–", "kcal")],
        chart=dict(type="calendar", start=str(start.date()), values=[float(daily.get(d, 0)) for d in days]),
    )


def sport_shift(df, f):
    df = df.assign(year=df.start.dt.year)
    cnt = df.groupby("year").size()
    years = sorted(cnt[cnt >= 10].index)  # skip near-empty first/last years
    if len(years) < 2:
        return None
    hours = df.groupby(["year", "sport"]).minutes.sum().unstack(fill_value=0) / 60
    top = hours.sum().sort_values(ascending=False).index[:5].tolist()
    share = hours.div(hours.sum(axis=1), axis=0)
    first, last = years[0], years[-1]
    # the sport whose share moved the most between the first and last year
    delta = (share.loc[last] - share.loc[first]).reindex(top).fillna(0)
    mover = delta.abs().idxmax()
    a, b = share.loc[first].get(mover, 0) * 100, share.loc[last].get(mover, 0) * 100
    if abs(b - a) < 10:
        return None
    return dict(
        id="sport_shift", score=55 + abs(b - a) / 2,
        title=f.t("Bạn đã đổi môn", "Your sport mix shifted"),
        headline=f.t(f"{f.sport(mover)}: {f.n(a)}% → {f.n(b)}% thời gian tập",
                     f"{f.sport(mover)}: {f.n(a)}% → {f.n(b)}% of training time"),
        detail=f.t(f"Tỉ trọng giờ tập theo năm, {first} so với {last}. Tổng giờ không cho thấy sự dịch chuyển này.",
                   f"Share of hours per year, {first} vs {last}. Totals hide this shift."),
        chart=dict(type="stack", labels=[str(y) for y in years],
                   series=[(f.sport(s), [float(share.loc[y].get(s, 0)) for y in years]) for s in top],
                   highlight=top.index(mover)),
    )


def golden_hour(df, f):
    d = df[df.start.dt.hour.between(5, 23)]
    m = d.groupby([d.start.dt.dayofweek, d.start.dt.hour]).size()
    if m.empty:
        return None
    grid = [[int(m.get((day, h), 0)) for h in range(5, 24)] for day in range(7)]
    (bd, bh) = m.idxmax()
    share = m.max() / len(d) * 100
    return dict(
        id="golden_hour", score=60,
        title=f.t("Giờ vàng", "Your golden hour"),
        headline=f.t(f"{DAYS['vi'][bd]} lúc {bh}h là khung giờ bạn tập nhiều nhất",
                     f"{DAYS['en'][bd]} at {bh}:00 is when you train most"),
        detail=f.t(f"Riêng ô này chiếm {f.n(share, 1)}% tổng số buổi. Số buổi theo ngày trong tuần và giờ bắt đầu.",
                   f"This one slot holds {f.n(share, 1)}% of all sessions. Sessions by weekday and start hour."),
        chart=dict(type="matrix", rows=DAYS[f.lang], cols=[str(h) for h in range(5, 24)], values=grid,
                   best=[int(bd), int(bh - 5)]),
    )


def turning_point(df, f):
    mc = df.groupby(df.start.dt.to_period("M")).size()
    months = pd.period_range(mc.index.min(), mc.index.max(), freq="M")
    mc = mc.reindex(months, fill_value=0)
    if len(mc) < 10:
        return None
    best, bi = 0, None
    for i in range(4, len(mc) - 3):
        before, after = mc.iloc[:i].mean(), mc.iloc[i:].mean()
        if min(before, after) < 1:
            continue
        ratio = (after + 0.5) / (before + 0.5)
        r = max(ratio, 1 / ratio)
        if r > best:
            best, bi = r, i
    if bi is None:
        return None
    before, after = mc.iloc[:bi].mean(), mc.iloc[bi:].mean()
    if best < 1.5 or min(before, after) < 1:  # "you just started" is not an insight
        return None
    up = after > before
    when = months[bi].strftime("%m/%Y")
    return dict(
        id="turning_point", score=60 + min(best, 4) * 8,
        title=f.t("Bước ngoặt", "The turning point"),
        headline=f.t(f"Từ {when} bạn tập {'nhiều' if up else 'ít'} gấp {f.n(max(after, before) / max(min(after, before), 0.1), 1)} lần",
                     f"Since {when} you train {f.n(max(after, before) / max(min(after, before), 0.1), 1)}× {'more' if up else 'less'}"),
        detail=f.t(f"{f.n(before, 1)} → {f.n(after, 1)} buổi mỗi tháng. Điểm gãy được tìm tự động, không phải theo năm.",
                   f"{f.n(before, 1)} → {f.n(after, 1)} sessions a month. The break point is detected, not a calendar year."),
        chart=dict(type="bars", labels=[p.strftime("%m/%y") for p in months], values=[int(v) for v in mc],
                   split=bi, means=[float(before), float(after)]),
    )


def consistency(df, f):
    weeks = df.set_index("start").minutes.resample("W-SUN").count()
    active = weeks > 0
    run_len = best = 0
    for a in active:
        run_len = run_len + 1 if a else 0
        best = max(best, run_len)
    gaps = df.start.diff().dt.days.dropna()
    weekend = df[df.start.dt.dayofweek >= 5].minutes.sum() / df.minutes.sum() * 100
    current = 0
    for a in active[::-1]:
        if not a:
            break
        current += 1
    return dict(
        id="consistency", score=50 + (20 if weekend > 50 else 0),
        title=f.t("Độ đều đặn", "Consistency"),
        headline=f.t(f"Chuỗi dài nhất {best} tuần liên tục có tập",
                     f"Longest streak: {best} weeks in a row"),
        detail=f.t(f"{f.n(active.mean() * 100)}% số tuần có ít nhất một buổi. Chuỗi hiện tại: {current} tuần. "
                   f"Lần nghỉ dài nhất: {int(gaps.max())} ngày. Cuối tuần chiếm {f.n(weekend)}% thời gian tập.",
                   f"{f.n(active.mean() * 100)}% of weeks have at least one session. Current streak: {current} weeks. "
                   f"Longest break: {int(gaps.max())} days. Weekends hold {f.n(weekend)}% of your time."),
        kpis=[(str(best), f.t("tuần liên tục", "week streak")), (str(current), f.t("chuỗi hiện tại", "current")),
              (str(int(gaps.max())), f.t("ngày nghỉ dài nhất", "longest break")),
              (f.n(weekend) + "%", f.t("vào cuối tuần", "on weekends"))],
        chart=None,
    )


def load_risk(df, f):
    w = df.set_index("start").minutes.resample("W-SUN").sum()
    chronic = w.rolling(4).mean().shift(1)
    acwr = (w / chronic).where(chronic > 60)
    w52 = w.iloc[-78:]
    flags = (acwr.reindex(w52.index) > 1.5).fillna(False)
    n = int((acwr > 1.5).sum())
    if acwr.notna().sum() < 8:
        return None
    return dict(
        id="load_risk", score=55 + min(n, 15) * 2,
        title=f.t("Tải tập và nguy cơ chấn thương", "Load spikes"),
        headline=f.t(f"{n} tuần bạn tăng tải quá nhanh", f"{n} weeks with a risky load spike"),
        detail=f.t("Tuần màu đỏ có tổng phút cao hơn 1,5 lần trung bình 4 tuần trước (ACWR > 1,5), "
                   "vùng các nghiên cứu gắn với nguy cơ chấn thương cao hơn. Tổng giờ mỗi tuần không cho thấy điều này.",
                   "Red weeks had over 1.5× the average of the 4 weeks before (ACWR > 1.5), a range linked to higher "
                   "injury risk. Weekly totals alone do not show it."),
        chart=dict(type="bars", labels=[d.strftime("%d/%m/%y" if f.lang == "vi" else "%y-%m-%d") for d in w52.index], values=[float(v) for v in w52],
                   flags=[bool(x) for x in flags], unit="min"),
    )


def hidden_fitness(df, f):
    r = runs(df)
    if len(r) < 12:
        return None
    # fitness = what you can do, so use each quarter's better runs (25th percentile), not easy days
    q = r.groupby(r.start.dt.to_period("Q")).agg(pace=("pace", "median"), eq5k=("eq5k", lambda x: x.quantile(.25)),
                                                km=("km", "median"), n=("pace", "size"))
    q = q[q.n >= 3]
    if len(q) < 4:
        return None
    a, b = q.iloc[:2].mean(), q.iloc[-2:].mean()
    pace_change = (b.pace - a.pace) * 60
    eq_change = (b.eq5k - a.eq5k) * 60 / 5  # seconds per km on a 5K-equivalent basis
    contradict = (pace_change > 0) != (eq_change > 0)
    score = 70 + (25 if contradict else 0) + min(abs(eq_change), 30) / 2
    if contradict and eq_change < 0:
        head = f.t(f"Pace trung bình chậm đi {f.n(abs(pace_change))}s/km, nhưng thực ra bạn nhanh hơn",
                   f"Your average pace got {f.n(abs(pace_change))}s/km slower, yet you are actually faster")
    elif eq_change < 0:
        head = f.t(f"Thể lực chạy tiến bộ {f.n(abs(eq_change))}s/km", f"Running fitness improved by {f.n(abs(eq_change))}s/km")
    else:
        head = f.t(f"Thể lực chạy giảm {f.n(abs(eq_change))}s/km", f"Running fitness dropped by {f.n(abs(eq_change))}s/km")
    return dict(
        id="hidden_fitness", score=score,
        title=f.t("Thể lực thật, đã trừ ảnh hưởng quãng đường", "True fitness, distance removed"),
        headline=head,
        detail=f.t(f"Chạy xa thì pace chậm hơn là bình thường (quãng trung vị {f.n(a.km, 1)} → {f.n(b.km, 1)} km). "
                   "Đường cam quy mỗi lần chạy về thành tích 5K tương đương (công thức Riegel), nên so sánh được công bằng.",
                   f"Longer runs are naturally slower (median {f.n(a.km, 1)} → {f.n(b.km, 1)} km). The orange line converts "
                   "every run to a 5K-equivalent pace (Riegel), so quarters compare fairly."),
        chart=dict(type="lines", labels=[str(p) for p in q.index], unit="min/km", invert=True,
                   series=[(f.t("Pace thô", "Raw pace"), [float(v) for v in q.pace], "muted"),
                           (f.t("Pace 5K tương đương", "5K-equivalent pace"), [float(v) / 5 for v in q.eq5k], "accent")]),
    )


def heartbeats_per_km(df, f):
    s = endurance_type(df)
    d = df[(df.sport == s) & df.hr.notna() & (df.km >= 1.5)].copy()
    if len(d) < 10:
        return None
    d["bpk"] = d.hr * d.minutes / d.km  # heartbeats spent per km
    q = d.groupby(d.start.dt.to_period("Q")).bpk.median()
    q = q[d.groupby(d.start.dt.to_period("Q")).size() >= 3]
    if len(q) < 4:
        return None
    first, last = q.iloc[:2].mean(), q.iloc[-2:].mean()
    ch = (last - first) / first * 100
    return dict(
        id="heartbeats", score=58 + min(abs(ch), 25),
        title=f.t("Nhịp tim cho mỗi km", "Heartbeats per km"),
        headline=f.t(f"Mỗi km {f.sport(s).lower()} tốn {f.n(last)} nhịp tim, {'ít' if ch < 0 else 'nhiều'} hơn {f.n(abs(ch))}% so với lúc đầu",
                     f"Each {f.sport(s).lower()} km costs {f.n(last)} heartbeats, {f.n(abs(ch))}% {'fewer' if ch < 0 else 'more'} than at the start"),
        detail=f.t("Nhịp tim trung bình × thời gian ÷ quãng đường. Càng thấp nghĩa là tim càng hiệu quả, "
                   "kể cả khi pace không đổi. Đây là chỉ số app thường không hiển thị.",
                   "Average HR × time ÷ distance. Lower means a more efficient heart even at the same pace; "
                   "most apps never show it."),
        chart=dict(type="lines", labels=[str(p) for p in q.index], unit=f.t("nhịp/km", "beats/km"), invert=True,
                   series=[(f.t("Nhịp tim mỗi km", "Heartbeats per km"), [float(v) for v in q], "accent")]),
    )


def time_of_day(df, f):
    r = runs(df)
    if len(r) < 15:
        return None
    bins = [(5, 9, f.t("Sáng sớm", "Early")), (9, 15, f.t("Trưa", "Midday")), (15, 19, f.t("Chiều", "Afternoon")),
            (19, 24, f.t("Tối", "Evening"))]
    rows = []
    for lo, hi, lab in bins:
        g = r[(r.start.dt.hour >= lo) & (r.start.dt.hour < hi)]
        if len(g) >= 3:
            rows.append((lab, float(g.eq5k.median() / 5), len(g)))
    if len(rows) < 2:
        return None
    best = min(rows, key=lambda x: x[1])
    worst = max(rows, key=lambda x: x[1])
    gap = (worst[1] - best[1]) * 60
    if gap < 5:
        return None
    return dict(
        id="time_of_day", score=55 + min(gap, 40) / 2,
        title=f.t("Bạn chạy nhanh nhất vào lúc nào", "When you run fastest"),
        headline=f.t(f"Chạy buổi {best[0].lower()} nhanh hơn buổi {worst[0].lower()} {f.n(gap)}s/km",
                     f"{best[0]} runs are {f.n(gap)}s/km faster than {worst[0].lower()} runs"),
        detail=f.t("Pace 5K tương đương theo khung giờ bắt đầu, đã loại ảnh hưởng của quãng đường.",
                   "5K-equivalent pace by start time, with distance effects removed."),
        chart=dict(type="hbars", labels=[x[0] for x in rows], values=[x[1] for x in rows], unit="min/km",
                   fmt="pace", best=rows.index(best), low_is_good=True),
    )


def seasonality(df, f):
    r = runs(df)
    if len(r) < 20:
        return None
    m = r.groupby(r.start.dt.month).eq5k.median() / 5
    cnt = r.groupby(r.start.dt.month).size()
    m = m[cnt >= 2]
    if len(m) < 6:
        return None
    gap = (m.max() - m.min()) * 60
    if gap < 10:
        return None
    return dict(
        id="seasonality", score=50 + min(gap, 60) / 3,
        title=f.t("Mùa ảnh hưởng tới bạn", "Seasons change your pace"),
        headline=f.t(f"Tháng {m.idxmax()} bạn chậm hơn tháng {m.idxmin()} tới {f.n(gap)}s/km",
                     f"In month {m.idxmax()} you are {f.n(gap)}s/km slower than in month {m.idxmin()}"),
        detail=f.t("Pace 5K tương đương theo tháng trong năm, gộp mọi năm. "
                   + ("Tháng chậm nhất rơi vào mùa nóng: nóng và ẩm làm tim phải làm việc nhiều hơn, đừng tự trách mình."
                      if 4 <= m.idxmax() <= 8 else "Hãy xem tháng chậm nhất có trùng mùa bận rộn, ốm hay nghỉ dài không."),
                   "5K-equivalent pace by calendar month across all years. "
                   + ("The slowest month falls in the hot season: heat and humidity make your heart work harder."
                      if 4 <= m.idxmax() <= 8 else "Check whether the slowest month matches a busy season, illness or a long break.")),
        chart=dict(type="bars", labels=[str(i) for i in m.index], values=[float(v) for v in m], unit="min/km",
                   fmt="pace", best=int(np.argmin(m.values)), worst=int(np.argmax(m.values))),
    )


def rest_effect(df, f):
    r = runs(df)
    if len(r) < 20:
        return None
    prev = df.set_index("start").sort_index()
    starts = prev.index.values
    rest = []
    for t in r.start.values:
        i = np.searchsorted(starts, t)
        rest.append((t - starts[i - 1]) / np.timedelta64(1, "D") if i > 0 else np.nan)
    r = r.assign(rest=rest).dropna(subset=["rest"])
    groups = [(f.t("Ngay hôm sau", "Next day"), r[r.rest < 1.5]), (f.t("Nghỉ 1 ngày", "1 rest day"), r[(r.rest >= 1.5) & (r.rest < 2.5)]),
              (f.t("Nghỉ 2-3 ngày", "2-3 rest days"), r[(r.rest >= 2.5) & (r.rest < 4.5)]), (f.t("Nghỉ 4+ ngày", "4+ rest days"), r[r.rest >= 4.5])]
    rows = [(lab, float(g.eq5k.median() / 5), len(g)) for lab, g in groups if len(g) >= 3]
    if len(rows) < 3:
        return None
    best = min(rows, key=lambda x: x[1])
    worst = max(rows, key=lambda x: x[1])
    gap = (worst[1] - best[1]) * 60
    if gap < 5:
        return None
    return dict(
        id="rest_effect", score=60 + min(gap, 40) / 2,
        title=f.t("Số ngày nghỉ lý tưởng", "Your ideal rest"),
        headline=f.t(f"Bạn chạy tốt nhất sau khi: {best[0].lower()}", f"You run best after: {best[0].lower()}"),
        detail=f.t(f"Nhanh hơn {f.n(gap)}s/km so với nhóm chậm nhất ({worst[0].lower()}). Tính theo số ngày từ hoạt động bất kỳ trước đó.",
                   f"{f.n(gap)}s/km faster than the slowest group ({worst[0].lower()}). Counted from your previous activity of any kind."),
        chart=dict(type="hbars", labels=[x[0] for x in rows], values=[x[1] for x in rows], unit="min/km",
                   fmt="pace", best=rows.index(best), low_is_good=True),
    )


def comeback(df, f):
    starts = df.start.sort_values().reset_index(drop=True)
    gaps = starts.diff().dt.days
    big = gaps[gaps >= 21]
    if big.empty:
        return None
    w = df.set_index("start").minutes.resample("W-SUN").sum()
    rows = []
    for i in big.index:
        t0, t1 = starts[i - 1], starts[i]
        before = w[(w.index > t0 - pd.Timedelta(days=56)) & (w.index <= t0 + pd.Timedelta(days=6))].mean()
        after = w[w.index > t1]
        back = after[after >= 0.8 * before]
        weeks = int(((back.index[0] - t1).days) // 7 + 1) if len(back) else None
        rows.append((t0, int(big[i]), weeks))
    longest = max(rows, key=lambda x: x[1])
    done = [x for x in rows if x[2]]
    avg = np.mean([x[2] for x in done]) if done else None
    return dict(
        id="comeback", score=45 + min(len(rows), 6) * 3,
        title=f.t("Những lần quay lại", "Comebacks"),
        headline=f.t(f"{len(rows)} lần nghỉ trên 3 tuần, dài nhất {longest[1]} ngày",
                     f"{len(rows)} breaks over 3 weeks, the longest {longest[1]} days"),
        detail=(f.t(f"Trung bình bạn cần {f.n(avg, 1)} tuần để lấy lại 80% khối lượng trước khi nghỉ.",
                    f"On average it took {f.n(avg, 1)} weeks to get back to 80% of your previous volume.")
                if avg else f.t("Bạn chưa lấy lại được khối lượng cũ sau lần nghỉ gần nhất.",
                                "You have not yet returned to your previous volume after the last break.")),
        chart=None,
    )


def race_prediction(df, f):
    r = runs(df, min_km=4.5)
    recent = r[r.start >= r.start.max() - pd.Timedelta(days=365)]
    if recent.empty:
        return None
    b = recent.sort_values("eq5k").iloc[0]
    pred = lambda d: b.minutes * (d / b.km) ** RIEGEL
    races = [("5K", 5), ("10K", 10), (f.t("Bán marathon", "Half marathon"), 21.0975), ("Marathon", 42.195)]
    return dict(
        id="race_prediction", score=65,
        title=f.t("Nếu thi đấu hôm nay", "If you raced today"),
        headline=f.t(f"10K khoảng {f.hms(pred(10))}", f"10K in about {f.hms(pred(10))}"),
        detail=f.t(f"Dựa trên lần chạy tốt nhất 12 tháng qua: {f.n(b.km, 2)} km trong {f.hms(b.minutes)} ({b.start:%d/%m/%Y}). "
                   "Công thức Riegel, chỉ là ước lượng: cự ly dài cần tập dài.",
                   f"From your best run of the last 12 months: {f.n(b.km, 2)} km in {f.hms(b.minutes)} ({b.start:%Y-%m-%d}). "
                   "Riegel formula, an estimate only: long races need long training."),
        kpis=[(f.hms(pred(d)), lab) for lab, d in races],
        chart=None,
    )


def year_over_year(df, f):
    end = df.start.max()
    cur = df[df.start > end - pd.Timedelta(days=90)]
    prev = df[(df.start > end - pd.Timedelta(days=455)) & (df.start <= end - pd.Timedelta(days=365))]
    if prev.empty or df.start.min() > end - pd.Timedelta(days=455):
        return None
    hc, hp = cur.minutes.sum() / 60, prev.minutes.sum() / 60
    ch = (hc - hp) / max(hp, 0.1) * 100
    return dict(
        id="yoy", score=50 + min(abs(ch), 200) / 10,
        title=f.t("So với cùng kỳ năm ngoái", "Same time last year"),
        headline=f.t(f"90 ngày qua: {f.n(hc)} giờ, {'+' if ch >= 0 else ''}{f.n(ch)}% so với cùng kỳ",
                     f"Last 90 days: {f.n(hc)} hours, {'+' if ch >= 0 else ''}{f.n(ch)}% year over year"),
        detail=f.t(f"{len(cur)} buổi so với {len(prev)} buổi cùng kỳ năm ngoái.",
                   f"{len(cur)} sessions vs {len(prev)} in the same window last year."),
        kpis=[(f.n(hc), f.t("giờ, 90 ngày qua", "hours, last 90d")), (f.n(hp), f.t("giờ, cùng kỳ", "hours, a year ago")),
              (str(len(cur)), f.t("buổi", "sessions")), (str(len(prev)), f.t("buổi cùng kỳ", "sessions a year ago"))],
        chart=None,
    )


FINDERS = [overview, hidden_fitness, rest_effect, heartbeats_per_km, turning_point, sport_shift, load_risk,
           time_of_day, seasonality, golden_hour, race_prediction, consistency, comeback, year_over_year]


def find_all(df: pd.DataFrame, lang="vi", limit=10):
    f = Fmt(lang)
    out = []
    for fn in FINDERS:
        try:
            r = fn(df, f)
        except Exception as e:  # one weak signal must not break the whole report
            print(f"insight {fn.__name__} skipped: {e}")
            r = None
        if r:
            out.append(r)
    head = [x for x in out if x["id"] == "overview"]
    rest = sorted([x for x in out if x["id"] != "overview"], key=lambda x: -x["score"])
    return head + rest[: limit - 1]
