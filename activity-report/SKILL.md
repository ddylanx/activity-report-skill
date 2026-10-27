---
name: activity-report
description: Turn Strava, Garmin, GPX/TCX/FIT or any running, cycling, walking or workout CSV into a detailed HTML report with charts and the hidden insights normal charts miss (true fitness trend, ideal rest days, load spikes, best time of day). Use when someone shares activity data or asks to analyse their training.
---

# Activity report

Builds one self-contained HTML report from a person's activity history. The report has charts plus 10 to 14 insights that ordinary app charts hide. Everything runs locally and needs only Python with pandas, so the data never leaves the machine.

## 1. Find the data

Accepted inputs, as a file or a folder:

- **Strava bulk export** (Settings → My Account → Download or Delete Your Account → Request archive). Use the unzipped folder or its `activities.csv`. English and Vietnamese exports both work.
- **Garmin Connect** `Activities.csv` (Activities → All Activities → Export CSV).
- **GPX, TCX or FIT files**, including `.gz`. A folder of them works. FIT needs `pip install fitdecode`.
- **Any CSV** with a date column plus some of: type or sport, distance (km or m), duration (seconds, minutes or h:mm:ss), average heart rate, elevation gain, calories, temperature. Headers are matched loosely.

If the person has not shared data yet, tell them how to get the Strava export above. Only read the activity files. Never open other personal files in an export, such as messages, contacts or logins.

## 2. Pick the time zone and language

- Strava stores UTC. Pass `--tz <hours>` for the person's local zone, for example `--tz 7` for Vietnam or `--tz -5` for New York. Infer it from their language or location, and ask only if you can't.
- `--lang vi` or `--lang en`, matching the conversation.

## 3. Run

```bash
pip install pandas            # once; add fitdecode for FIT files
python scripts/report.py <path> --tz 7 --lang vi --out activity-report.html
```

It writes `activity-report.html` (the report) and `activity-report.json` (the insights as data), then prints a short summary to stdout.

Options:

- `--limit N`: the number of insights to keep (default 12). Insights are ranked by how surprising they are.
- `--title "..."`: a custom report title.

## 4. Read the results before you hand them over

Check the printed summary and open the HTML. Confirm the numbers make sense: sport counts, date range, and nothing absurd such as a 2-minute marathon. Then:

- Tell the person the 3 most surprising insights in plain words.
- Say where the report file is.
- Mention the caveats when relevant:
  - Riegel race predictions are estimates.
  - ACWR load spikes are a risk signal, not a diagnosis.
  - Insights based on few activities (under about 20 runs) are weak.

If the data does not support an insight, the script drops it on purpose. Don't invent replacements.

## What the insights are

| id | Insight | Why a normal chart misses it |
|---|---|---|
| overview | Totals and a 12-month calendar heatmap | (baseline) |
| hidden_fitness | Quarterly 5K-equivalent pace (Riegel) next to raw pace | Longer runs make raw pace look slower, even when fitness improves |
| heartbeats | Heartbeats spent per km (avg HR × time ÷ distance) | Shows heart efficiency at any pace; apps rarely show it |
| rest_effect | Distance-adjusted pace by days since the previous activity | Finds the person's ideal rest |
| time_of_day | Distance-adjusted pace by start time | Raw pace mixes easy and hard runs |
| seasonality | Distance-adjusted pace by calendar month | Separates heat and season from fitness |
| turning_point | Automatically detected change in monthly sessions | Calendar-year totals blur when the habit really changed |
| sport_shift | Each sport's share of training time per year | Total hours hide a shift between sports |
| load_risk | Weeks with acute:chronic workload over 1.5 | A weekly total looks fine while the jump is risky |
| golden_hour | Weekday × hour matrix and its peak | Habits hide in the timestamps |
| consistency | Longest weekly streak, current streak, longest break, weekend share | Not shown as a single number anywhere |
| comeback | Breaks over 3 weeks and the weeks needed to regain 80% of volume | Needs gap detection |
| race_prediction | 5K, 10K, half and full marathon estimates from the best recent run | Needs a formula |
| yoy | Last 90 days against the same 90 days a year earlier | Apps compare calendar periods only |

Running insights use the canonical sport `run`. The heartbeat insight uses the main distance sport: run, ride, walk or hike, whichever has at least 10 sessions. Generic "Workout" activities whose name says Badminton, Tennis, Football, Yoga, etc. are re-labelled to that sport.

## Extending

- A new insight is a function in `scripts/insights.py` that returns a dict with these keys:
  - `id`, `score`, `title`, `headline`, `detail`;
  - optional `kpis`;
  - optional `chart`, using one of the `scripts/charts.py` types: calendar, bars, hbars, lines, matrix, stack.

  Add it to `FINDERS`. Return `None` when the data can't support it.
- A new input format is a reader in `scripts/load.py` that returns the normalized columns: `start, sport, name, km, minutes, hr, elev, kcal, temp`.
