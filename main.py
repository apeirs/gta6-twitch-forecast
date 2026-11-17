"""gta6-twitch-ccu-forecast-01: release-day Twitch viewers from kernel-weighted past launches (Python 3.13, stdlib only).

For hours 2..24 of the release day (UTC) the forecast is a log-normal fan around hour 1's print p1:

    q_tau(h) = p1 * exp(m_h + z_tau * s_h)

where m_h and s_h are the weighted mean and spread of log(count_h / count_hour1) over the case's comparables (past
launches' release days). Each comparable is weighted by a Gaussian kernel on how much its pre-release shape at hour 1
looks like this case's: hour 1 over the hour before, over the median of the day before, over the max of the last six
hours, and the size of hour 1. Anything that goes wrong falls back to the house baseline's widening fan around p1.

Deterministic (no randomness, no clock, inputs read in name order) and fast (a few ms a case).

Run locally:
    mkdir -p out && MAKEFUN_INPUT_DIR=../kit/input MAKEFUN_OUTPUT_DIR=out python3 main.py
"""

import json
import math
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

INPUT_DIR = Path(os.environ.get("MAKEFUN_INPUT_DIR", "/input"))
OUTPUT_DIR = Path(os.environ.get("MAKEFUN_OUTPUT_DIR", "/output"))

LEVELS = [0.05, 0.25, 0.5, 0.75, 0.95]
Z = [-1.645, -0.674, 0.0, 0.674, 1.645]
HOURS = list(range(2, 25))
H = 3600

FALLBACK_SIGMA = 0.15  # the baseline's log spread per sqrt(hour), used only when the model path fails
BANDWIDTH = 1.0        # kernel bandwidth, in units of each feature's spread across the comparables
SPREAD_FLOOR = 0.05   # smallest log spread the model may write for any hour
SPREAD_SCALE = 0.75    # the kernel mixes neighbours that differ in kind; their raw weighted spread runs ~1.3x too
                       # wide for launches with an audience at hour 1 (leave-one-out 90% coverage 0.96 -> 0.90)
MIN_TRUTH_HOURS = 12   # a comparable needs at least this many of hours 2..24 to be a training curve


# ----------------------------------------------------------------------------------------------- small helpers
def parse_ts(s) -> int | None:
    """ISO 8601 UTC timestamp -> whole seconds since the epoch, or None when it cannot be read."""
    if not isinstance(s, str) or not s:
        return None
    try:
        dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return int(dt.timestamp())


def num(x) -> float | None:
    """A finite non-negative number, or None."""
    if isinstance(x, bool) or not isinstance(x, (int, float)):
        return None
    x = float(x)
    if not math.isfinite(x) or x < 0:
        return None
    return x


def median(xs: list[float]) -> float:
    s = sorted(xs)
    n = len(s)
    return s[n // 2] if n % 2 else 0.5 * (s[n // 2 - 1] + s[n // 2])


def round2(x: float) -> float | int:
    """x rounded to 2 decimals, half up (as the starter rounds), an int when whole."""
    scaled = x * 100
    whole = math.floor(scaled)
    if scaled - whole >= 0.5:
        whole += 1
    value = whole / 100
    return int(value) if value.is_integer() else value


def hourly_series(points, ts_key: str) -> dict[int, float]:
    """Points [{ts_key, viewers}] -> {hour start (epoch s): mean viewers of the points in that hour}."""
    acc: dict[int, list[float]] = {}
    for p in points or []:
        if not isinstance(p, dict):
            continue
        t = parse_ts(p.get(ts_key))
        v = num(p.get("viewers"))
        if t is None or v is None:
            continue
        acc.setdefault(t - t % H, []).append(v)
    return {t: sum(vs) / len(vs) for t, vs in acc.items()}


# ----------------------------------------------------------------------------------------------- the model
def features(series: dict[int, float], day: int, p1: float) -> list[float | None]:
    """Pre-release shape at the end of hour 1: log p1 over the hour before, the day before's median, the last six
    hours' max, and log p1 itself. A feature with no data is None."""
    lp1 = math.log(max(p1, 1.0))
    prev = series.get(day - H)
    if prev is None:  # sparse history: the latest point of the 6 hours before
        for k in range(2, 7):
            if day - k * H in series:
                prev = series[day - k * H]
                break
    day_before = [series[t] for t in range(day - 24 * H, day, H) if t in series]
    last6 = [series[t] for t in range(day - 6 * H, day, H) if t in series]
    return [
        lp1 - math.log(max(prev, 1.0)) if prev is not None else None,
        lp1 - math.log(max(median(day_before), 1.0)) if len(day_before) >= 3 else None,
        lp1 - math.log(max(max(last6), 1.0)) if last6 else None,
        lp1,
    ]


def has_pc(platforms) -> float:
    """1 when a launch was on PC too. PC launches often unlock at one global time, so their release-day curve has
    another shape than a console launch rolling through the time zones."""
    return 1.0 if "PC" in str(platforms or "") else 0.0


def training_curves(case: dict, day: int) -> list[tuple[list, dict[int, float]]]:
    """Each usable comparable's (features, {h: log(count_h / count_hour1)})."""
    game = case.get("game") if isinstance(case.get("game"), dict) else {}
    own_name = game.get("name")
    out = []
    for comp in case.get("comparables") or []:
        if not isinstance(comp, dict) or (own_name and comp.get("name") == own_name):
            continue
        cday = parse_ts(comp.get("day_start"))
        if cday is None or cday == day:  # never the case's own launch
            continue
        series = hourly_series(comp.get("hourly"), "from")
        p1 = series.get(cday)
        if p1 is None:
            continue
        lp1 = math.log(max(p1, 1.0))
        ratios = {}
        for h in HOURS:
            v = series.get(cday + (h - 1) * H)
            if v is not None:
                ratios[h] = math.log(max(v, 1.0)) - lp1
        if len(ratios) < MIN_TRUTH_HOURS:  # e.g. the GTA VI category's own pre-release history
            continue
        out.append((features(series, cday, p1) + [has_pc(comp.get("platforms"))], ratios))
    return out


def model_fan(case: dict, series: dict[int, float], day: int, p1: float) -> list[tuple[float, float]] | None:
    """[(m_h, s_h)] for hours 2..24, or None when there is nothing to learn from."""
    train = training_curves(case, day)
    if len(train) < 3:
        return None
    # Every case of this contest is a console launch (GTA VI: PS5 and Xbox Series): PC only if the case says so.
    game = case.get("game") if isinstance(case.get("game"), dict) else {}
    x = features(series, day, p1) + [has_pc(game.get("platforms"))]
    nf = len(x)
    scales = []
    for k in range(nf):
        vals = [f[k] for f, _ in train if f[k] is not None]
        if len(vals) >= 2:
            mu = sum(vals) / len(vals)
            sd = math.sqrt(sum((v - mu) ** 2 for v in vals) / (len(vals) - 1))
        else:
            sd = 1.0
        scales.append(max(sd, 0.1))
    d2s = []
    for f, _ in train:
        d2 = 0.0
        for k in range(nf):
            if x[k] is None:
                continue
            if f[k] is None:
                d2 += 1.0
            else:
                d2 += ((x[k] - f[k]) / scales[k]) ** 2
        d2s.append(d2 / (BANDWIDTH * BANDWIDTH))
    d0 = min(d2s)
    weights = [math.exp(-0.5 * (d - d0)) for d in d2s]

    fan = []
    for h in HOURS:
        pairs = [(w, r[h]) for w, (_, r) in zip(weights, train) if h in r]
        sw = sum(w for w, _ in pairs)
        if sw <= 0:
            return None
        m = sum(w * r for w, r in pairs) / sw
        var = sum(w * (r - m) ** 2 for w, r in pairs) / sw
        fan.append((m, max(SPREAD_SCALE * math.sqrt(var), SPREAD_FLOOR)))
    return fan


# ----------------------------------------------------------------------------------------------- the case
def hour1_print(case: dict, series: dict[int, float], day: int | None) -> float:
    """Hour 1's print; a missing or zero one falls back to hour 1's history, then the last positive history point."""
    for k in case.get("known") or []:
        if isinstance(k, dict) and k.get("hour") == 1 and (num(k.get("viewers")) or 0) > 0:
            return max(num(k["viewers"]), 1.0)
    if day is not None and series.get(day, 0) > 0:
        return max(series[day], 1.0)
    for p in reversed(case.get("history") or []):
        if isinstance(p, dict) and (num(p.get("viewers")) or 0) > 0:
            return max(num(p["viewers"]), 1.0)
    return 1.0


def fallback_fan() -> list[tuple[float, float]]:
    return [(0.0, FALLBACK_SIGMA * math.sqrt(h - 1)) for h in HOURS]


def rows_from_fan(p1: float, fan: list[tuple[float, float]]) -> list[dict]:
    rows = []
    for h, (m, s) in zip(HOURS, fan):
        qs, lo = [], 0.01
        for z in Z:
            v = p1 * math.exp(max(min(m + z * s, 30.0), -30.0))
            v = round2(min(max(v, 0.01), 1e9))
            v = max(v, lo)
            qs.append(v)
            lo = v
        rows.append({"hour": h, "q": qs})
    return rows


def forecast_case(case: dict) -> dict:
    """The forecast {"hours": [...]} of one case. Never raises."""
    p1 = 1.0
    try:
        day = parse_ts(case.get("day_start"))
        if day is None:
            cp = parse_ts(case.get("checkpoint"))
            day = cp - H if cp is not None else None
        series = hourly_series(case.get("history_hourly"), "from")
        if not series:
            series = hourly_series(case.get("history"), "at")
        p1 = hour1_print(case, series, day)
        if day is not None:
            series[day] = p1  # hour 1 is the known print, whatever the history says
        fan = model_fan(case, series, day, p1) if day is not None else None
        if fan is None or not all(math.isfinite(m) and math.isfinite(s) for m, s in fan):
            fan = fallback_fan()
        return {"hours": rows_from_fan(p1, fan)}
    except Exception:
        return {"hours": rows_from_fan(p1, fallback_fan())}


def main() -> None:
    try:
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    except OSError:
        pass
    for path in sorted(INPUT_DIR.glob("*.in")):
        try:
            case = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(case, dict):
                case = {}
        except Exception:
            case = {}
        forecast = forecast_case(case)
        (OUTPUT_DIR / f"{path.stem}.out").write_text(json.dumps(forecast, separators=(",", ":")) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
