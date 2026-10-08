"""Deterministic bandwidth models. All timestamps are UTC; rates are decimal Mbps."""
import calendar
import math
from collections import defaultdict
from datetime import datetime, timezone

REGIONS = ('Group 1', 'Group 2', 'China', 'Vietnam', 'Morocco')
MODELS = ('bursting-2027', 'enforced-pool', 'site', 'classic-p95')


def p95(values):
    """Discard floor(5% * n) highest buckets; return the highest remaining."""
    ordered = sorted(values)
    return ordered[len(ordered) - math.floor(len(ordered) * .05) - 1] if ordered else None


def month_bounds(month):
    start = datetime.strptime(month, '%Y-%m').replace(tzinfo=timezone.utc)
    end = start.replace(year=start.year + (start.month == 12), month=start.month % 12 + 1)
    return int(start.timestamp()), int(end.timestamp())


def analyze(sites, samples, month, scenario):
    start, end = month_bounds(month)
    growth = 1 + scenario.get('growth', 0) / 100
    headroom = 1 + scenario.get('headroom', 20) / 100
    model = scenario.get('model', 'bursting-2027')
    if model not in MODELS:
        raise ValueError('Unknown license model')
    groups, rows = defaultdict(list), []
    by_site = defaultdict(list)
    for sample in samples:
        if start <= sample['ts'] < end:
            by_site[str(sample['site_id'])].append(sample)
    for site in sites:
        site = dict(site)
        override = scenario.get('sites', {}).get(str(site['id']), {})
        region = override.get('region', site.get('region', 'Unassigned'))
        limit = float(override.get('capacity', site.get('capacity', 100)))
        values, days = [], defaultdict(list)
        for sample in by_site[str(site['id'])]:
            value = max(sample['up'], sample['down']) * growth
            values.append(value)
            day = datetime.fromtimestamp(sample['ts'], timezone.utc).strftime('%Y-%m-%d')
            days[day].append(value)
        daily = {day: p95(v) for day, v in days.items()}
        peak = max(values, default=0)
        metric = max(daily.values(), default=0) if model == 'bursting-2027' else (p95(values) or 0) if model == 'classic-p95' else peak
        count = len(values)
        expected = (end - start) // 300
        row = dict(id=str(site['id']), name=site['name'], region=region, capacity=limit,
                   daily=daily, day_counts={day: len(v) for day, v in days.items()}, peak=peak, p95=p95(values) or 0, measured=metric,
                   recommendation=math.ceil(metric * headroom / 10) * 10,
                   coverage=round(count / expected * 100, 2), samples=count,
                   complete_days=sum(len(v) == 288 for v in days.values()),
                   over_minutes=sum(v > limit for v in values) * 5,
                   excess=max(0, metric - limit), type=site.get('type', 'Unknown'))
        rows.append(row)
        groups[region].append(row)
    pools = []
    for region, members in sorted(groups.items()):
        capacity = float(scenario.get('pools', {}).get(region, 500))
        all_days = sorted({day for s in members for day in s['daily']})
        # Missing site days are flagged in coverage; no claim of a complete billable month.
        aggregates = [{'day': day, 'mbps': sum(s['daily'].get(day, 0) for s in members),
                       'complete': all(s['day_counts'].get(day, 0) == 288 for s in members)} for day in all_days]
        daily_usage = max((d['mbps'] for d in aggregates), default=0)
        allocation = sum(s['capacity'] for s in members)
        measured = daily_usage if model == 'bursting-2027' else allocation if model == 'enforced-pool' else sum(s['measured'] for s in members)
        pools.append(dict(region=region, capacity=capacity, measured=measured,
                          allocation=allocation, recommendation=(sum(s['recommendation'] for s in members) if model in ('site', 'enforced-pool', 'classic-p95') else math.ceil(measured * headroom / 10) * 10),
                          excess=max(0, measured - capacity), daily=aggregates,
                          supported=not (model == 'enforced-pool' and region in ('China', 'Vietnam', 'Morocco')),
                          contributors=[{'name': s['name'], 'mbps': s['daily'].get(max(aggregates, key=lambda d: d['mbps'])['day'], 0)} for s in members] if aggregates else []))
    warnings = []
    if model in ('site', 'enforced-pool'):
        warnings.append('Observed throughput may already be constrained by current site limits; it cannot reveal all latent demand.')
    if any(s['coverage'] < 100 for s in rows):
        warnings.append('Incomplete month: missing buckets are excluded, never replaced with zero. Results are provisional and may underestimate requirements.')
    if any(s['region'] not in REGIONS for s in rows):
        warnings.append('Assign every site to a verified license region before using recommendations.')
    if model == 'classic-p95':
        warnings.append('Classic monthly site P95 is an educational comparison, not the documented 2027 Cato pool rule.')
    if model == 'bursting-2027':
        warnings.append('Bursting rule profile: Cato Usage Measurement updated October 4, 2026; scheduled for January 2027. Validate the profile against your agreement and CMA.')
        if any('CROSS_CONNECT' in s['type'] or s['region'] in ('China', 'Vietnam', 'Morocco') for s in rows):
            warnings.append('Cloud Interconnect and stand-alone country sites retain per-site enforcement. Check their configured limits as well as pool usage.')
    if model == 'enforced-pool' and any(not p['supported'] for p in pools):
        warnings.append('Legacy pooled licenses are not supported for stand-alone country groups; use site licensing there.')
    trend = defaultdict(float)
    for sample in samples:
        if start <= sample['ts'] < end:
            trend[sample['ts']] += max(sample['up'], sample['down']) * growth
    return dict(month=month, model=model, sites=rows, pools=pools, warnings=warnings,
                series=[{'ts': ts, 'mbps': v} for ts, v in sorted(trend.items())],
                peak=max(trend.values(), default=0), total_recommended=sum(p['recommendation'] for p in pools),
                complete=bool(rows) and all(s['coverage'] == 100 for s in rows))
