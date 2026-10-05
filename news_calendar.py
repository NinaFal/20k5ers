"""
Calendar of high-impact releases, in the timezone of the releasing country.

Times are defined in local release time (8:30 New York for US and Canadian
data) and converted to UTC per date, so summer and winter time are right
without a manual change. The old backtest window blocked NFP at 13:00-15:00
UTC, which in US summer time misses the 12:30 UTC release entirely: on
2015-08-07 12:30 UTC six funded accounts in the random study died on it.

Rule-based events (no data source needed):
  NFP   first Friday of the month, 8:30 New York            USD
  LFS   Canadian jobs, first Friday of the month, 8:30 NY   CAD (usually same
        day as NFP; occasionally the week after, which this rule misses)
  ISM   ISM manufacturing, first US business day, 10:00 NY  USD
Date lists:
  FOMC  decision 14:00 New York                             USD
  ECB   decision 13:45 Frankfurt (since 2022: 14:15)        EUR

Not covered: US CPI (date varies by BLS schedule, no rule). Add its dates to
EXTRA_EVENTS when a source is available.
"""
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

NY = ZoneInfo("America/New_York")
FRA = ZoneInfo("Europe/Berlin")

FOMC = {
    (2015, 1, 28), (2015, 3, 18), (2015, 4, 29), (2015, 6, 17), (2015, 7, 29), (2015, 9, 17), (2015, 10, 28), (2015, 12, 16),
    (2016, 1, 27), (2016, 3, 16), (2016, 4, 27), (2016, 6, 15), (2016, 7, 27), (2016, 9, 21), (2016, 11, 2), (2016, 12, 14),
    (2017, 2, 1), (2017, 3, 15), (2017, 5, 3), (2017, 6, 14), (2017, 7, 26), (2017, 9, 20), (2017, 11, 1), (2017, 12, 13),
    (2018, 1, 31), (2018, 3, 21), (2018, 5, 2), (2018, 6, 13), (2018, 8, 1), (2018, 9, 26), (2018, 11, 8), (2018, 12, 19),
    (2019, 1, 30), (2019, 3, 20), (2019, 5, 1), (2019, 6, 19), (2019, 7, 31), (2019, 9, 18), (2019, 10, 30), (2019, 12, 11),
    (2020, 1, 29), (2020, 3, 15), (2020, 4, 29), (2020, 6, 10), (2020, 7, 29), (2020, 9, 16), (2020, 11, 5), (2020, 12, 16),
    (2021, 1, 27), (2021, 3, 17), (2021, 4, 28), (2021, 6, 16), (2021, 7, 28), (2021, 9, 22), (2021, 11, 3), (2021, 12, 15),
    (2022, 1, 26), (2022, 3, 16), (2022, 5, 4), (2022, 6, 15), (2022, 7, 27), (2022, 9, 21), (2022, 11, 2), (2022, 12, 14),
    (2023, 2, 1), (2023, 3, 22), (2023, 5, 3), (2023, 6, 14), (2023, 7, 26), (2023, 9, 20), (2023, 11, 1), (2023, 12, 13),
    (2024, 1, 31), (2024, 3, 20), (2024, 5, 1), (2024, 6, 12), (2024, 7, 31), (2024, 9, 18), (2024, 11, 7), (2024, 12, 18),
    (2025, 1, 29), (2025, 3, 19), (2025, 5, 7), (2025, 6, 18), (2025, 7, 30), (2025, 9, 17), (2025, 10, 29), (2025, 12, 10),
}
ECB = {
    (2015, 1, 22), (2015, 3, 5), (2015, 4, 15), (2015, 6, 3), (2015, 7, 16), (2015, 9, 3), (2015, 10, 22), (2015, 12, 3),
    (2016, 1, 21), (2016, 3, 10), (2016, 4, 21), (2016, 6, 2), (2016, 7, 21), (2016, 9, 8), (2016, 10, 20), (2016, 12, 8),
    (2017, 1, 19), (2017, 3, 9), (2017, 4, 27), (2017, 6, 8), (2017, 7, 20), (2017, 9, 7), (2017, 10, 26), (2017, 12, 14),
    (2018, 1, 25), (2018, 3, 8), (2018, 4, 26), (2018, 6, 14), (2018, 7, 26), (2018, 9, 13), (2018, 10, 25), (2018, 12, 13),
    (2019, 1, 24), (2019, 3, 7), (2019, 4, 10), (2019, 6, 6), (2019, 7, 25), (2019, 9, 12), (2019, 10, 24), (2019, 12, 12),
    (2020, 1, 23), (2020, 3, 12), (2020, 4, 30), (2020, 6, 4), (2020, 7, 16), (2020, 9, 10), (2020, 10, 29), (2020, 12, 10),
    (2021, 1, 21), (2021, 3, 11), (2021, 4, 22), (2021, 6, 10), (2021, 7, 22), (2021, 9, 9), (2021, 10, 28), (2021, 12, 16),
    (2022, 2, 3), (2022, 3, 10), (2022, 4, 14), (2022, 6, 9), (2022, 7, 21), (2022, 9, 8), (2022, 10, 27), (2022, 12, 15),
    (2023, 2, 2), (2023, 3, 16), (2023, 5, 4), (2023, 6, 15), (2023, 7, 27), (2023, 9, 14), (2023, 10, 26), (2023, 12, 14),
    (2024, 1, 25), (2024, 3, 7), (2024, 4, 11), (2024, 6, 6), (2024, 7, 18), (2024, 9, 12), (2024, 10, 17), (2024, 12, 12),
    (2025, 1, 30), (2025, 3, 6), (2025, 4, 17), (2025, 6, 5), (2025, 7, 24), (2025, 9, 11), (2025, 10, 30), (2025, 12, 18),
}
# (y, m, d, "HH:MM", tz, [currencies]) — e.g. CPI dates once a source exists.
EXTRA_EVENTS = []

_US_HOLIDAYS_FIXED = {(1, 1), (7, 4), (12, 25)}


def _utc(d, hhmm, tz):
    h, m = map(int, hhmm.split(":"))
    return datetime.combine(d, time(h, m), tzinfo=tz).astimezone(timezone.utc)


def _first_weekday(y, m, weekday):
    d = date(y, m, 1)
    return d + timedelta(days=(weekday - d.weekday()) % 7)


def _first_business_day(y, m):
    d = date(y, m, 1)
    while d.weekday() >= 5 or (d.month, d.day) in _US_HOLIDAYS_FIXED:
        d += timedelta(days=1)
    return d


def events_on(d):
    """[(utc_datetime, name, [currencies])] for a calendar date."""
    out = []
    if d == _first_weekday(d.year, d.month, 4):
        out.append((_utc(d, "08:30", NY), "NFP", ["USD"]))
        out.append((_utc(d, "08:30", NY), "LFS", ["CAD"]))
    if d == _first_business_day(d.year, d.month):
        out.append((_utc(d, "10:00", NY), "ISM", ["USD"]))
    if (d.year, d.month, d.day) in FOMC:
        out.append((_utc(d, "14:00", NY), "FOMC", ["USD"]))
    if (d.year, d.month, d.day) in ECB:
        out.append((_utc(d, "14:15" if d.year >= 2022 else "13:45", FRA), "ECB", ["EUR"]))
    for y, m, dd, hhmm, tzname, ccys in EXTRA_EVENTS:
        if (y, m, dd) == (d.year, d.month, d.day):
            out.append((_utc(d, hhmm, ZoneInfo(tzname)), "EXTRA", list(ccys)))
    return out


def upcoming(now_utc, before_min):
    """Events whose release falls in (now, now + before_min]."""
    out = []
    for d in {now_utc.date(), (now_utc + timedelta(minutes=before_min)).date()}:
        for t, name, ccys in events_on(d):
            if now_utc < t <= now_utc + timedelta(minutes=before_min):
                out.append((t, name, ccys))
    return out


def in_blackout(now_utc, before_min=15, after_min=60):
    """Currencies blocked for NEW entries around a release, or []."""
    ccys = []
    for d in {now_utc.date(), (now_utc - timedelta(minutes=after_min)).date(),
              (now_utc + timedelta(minutes=before_min)).date()}:
        for t, name, cs in events_on(d):
            if t - timedelta(minutes=before_min) <= now_utc <= t + timedelta(minutes=after_min):
                ccys += cs
    return sorted(set(ccys))
