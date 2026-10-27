"""Write a synthetic two-year activity history (generic CSV) for trying the skill without real data."""
import csv
import random
import sys
from datetime import datetime, timedelta

random.seed(7)
out = sys.argv[1] if len(sys.argv) > 1 else "sample_activities.csv"
start = datetime(2024, 9, 1, 6, 0)
rows, fitness, t = [], 6.6, start
while t < datetime(2026, 10, 18):
    t += timedelta(days=random.choice([1, 1, 2, 2, 3, 4]))
    if datetime(2025, 5, 10) < t < datetime(2025, 6, 20):  # a break, to show the comeback insight
        continue
    fitness = max(5.2, fitness - 0.004)
    hour = random.choice([5, 6, 6, 18, 19, 20])
    when = t.replace(hour=hour, minute=random.randint(0, 50))
    sport = random.choices(["Run", "Ride", "Walk", "Workout"], [6, 2, 1, 2])[0]
    if sport == "Run":
        km = round(random.choice([5, 5, 6, 8, 10, 12, 16]) * random.uniform(0.9, 1.1), 2)
        heat = 0.25 if when.month in (4, 5, 6, 7) else 0
        pace = fitness * (km / 5) ** 0.06 + heat + (0.15 if hour < 7 else 0) + random.uniform(-0.2, 0.3)
        mins, hr = km * pace, random.randint(140, 165)
    elif sport == "Ride":
        km = round(random.uniform(20, 60), 1)
        mins, hr = km / random.uniform(22, 28) * 60, random.randint(120, 150)
    elif sport == "Walk":
        km = round(random.uniform(3, 7), 1)
        mins, hr = km * 11.5, random.randint(95, 115)
    else:
        km, mins, hr = "", random.randint(35, 70), random.randint(110, 150)
    rows.append([when.strftime("%Y-%m-%d %H:%M:%S"), sport, f"{sport} {when:%b %d}", km,
                 int(mins * 60), hr, random.randint(0, 120) if km else "", int(mins * 10)])

with open(out, "w", newline="") as fh:
    w = csv.writer(fh)
    w.writerow(["start_time", "sport", "name", "distance_km", "moving_time", "avg_hr", "elevation_gain", "calories"])
    w.writerows(rows)
print(f"wrote {len(rows)} activities to {out}")
