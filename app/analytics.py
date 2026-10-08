"""Versioned, evidence-aware bandwidth models; UTC timestamps, decimal Mbps."""
import math
from collections import defaultdict
from datetime import datetime, timezone

REGIONS = ('Group 1', 'Group 2', 'China', 'Vietnam', 'Morocco')
MODELS = ('bursting-2027', 'enforced-pool', 'site', 'classic-p95')
PROFILE = 'cato-2026-10-04'
SOURCE = 'https://knowledge.catonetworks.com/docs/usage-measurement'


def p95(values):
    ordered = sorted(values)
    return ordered[len(ordered) - math.floor(len(ordered) * .05) - 1] if ordered else None


def month_bounds(month):
    start = datetime.strptime(month, '%Y-%m').replace(tzinfo=timezone.utc)
    end = start.replace(year=start.year + (start.month == 12), month=start.month % 12 + 1)
    return int(start.timestamp()), int(end.timestamp())


def rounded(value, headroom, increment):
    return math.ceil(value * headroom / increment) * increment


def analyze(sites, samples, month, scenario, include_series=True):
    start, end = month_bounds(month)
    model = scenario.get('model', 'site')
    headroom = 1 + float(scenario.get('headroom', 20)) / 100
    increment = float(scenario.get('increment', 10))
    if model not in MODELS:
        raise ValueError('Unknown model')
    groups, rows, by_site, trend = defaultdict(list), [], defaultdict(list), defaultdict(float)
    for sample in samples:
        if start <= sample['ts'] < end:
            by_site[str(sample['site_id'])].append(sample)
    expected = (end - start) // 300
    for site in sites:
        sid = str(site['id'])
        override = scenario.get('sites', {}).get(sid, {})
        region = override.get('region', site.get('region', 'Unassigned'))
        capacity = override.get('capacity', site.get('capacity'))
        capacity = float(capacity) if capacity is not None else None
        kind = override.get('type', site.get('type', 'Unknown'))
        verified = bool(override.get('verified', False))
        site_growth = 1 + float(override.get('growth', scenario.get('region_growth', {}).get(region, scenario.get('growth', 0)))) / 100
        days, values = defaultdict(list), []
        for sample in by_site[sid]:
            value = max(sample['up'], sample['down']) * site_growth
            values.append(value)
            day = datetime.fromtimestamp(sample['ts'], timezone.utc).strftime('%Y-%m-%d')
            days[day].append(value)
            trend[sample['ts']] += value
        counts = {day:len(v) for day,v in days.items()}
        daily = {day:p95(v) for day,v in days.items() if len(v) == 288}
        partial_daily = {day:p95(v) for day,v in days.items() if len(v) != 288}
        peak = max(values, default=0)
        observed = max(daily.values(), default=0) if model == 'bursting-2027' else (p95(values) or 0) if model == 'classic-p95' else peak
        complete = len(values) == expected
        constrained = bool(override.get('enforced')) or model in ('site','enforced-pool') or region in ('China','Vietnam','Morocco') or 'CROSS_CONNECT' in kind or kind == 'CLOUD_INTERCONNECT'
        type_known = kind.startswith(('SOCKET_','VSOCKET_','IPSEC_','CROSS_CONNECT')) or kind=='CLOUD_INTERCONNECT'
        eligible = complete and verified and not (model=='enforced-pool' and region in ('China','Vietnam','Morocco')) and region in REGIONS and type_known and model != 'classic-p95' and bool(scenario.get('model_verified'))
        recommendation = rounded(observed, headroom, increment) if eligible else None
        # Bursting country/interconnect sites must meet both usage and fixed site enforcement.
        limit_basis = peak if constrained else observed
        row = dict(id=sid,name=site['name'],region=region,capacity=capacity,type=kind,
                   source=site.get('source','legacy-unverified'),verified=verified,
                   daily=daily,partial_daily=partial_daily,day_counts=counts,peak=peak,
                   p95=p95(values) or 0,observed=observed,measured=observed if complete else None,
                   recommendation=recommendation,
                   site_limit_recommendation=rounded(peak,headroom,increment) if eligible and constrained else None,
                   constrained=constrained,coverage=round(len(values)/expected*100,4),samples=len(values),expected=expected,
                   complete_days=len(daily),missing_buckets=expected-len(values),zero_buckets=sum(v==0 for v in values),
                   longest_gap_minutes=longest_gap([s['ts'] for s in by_site[sid]],start,end),
                   over_minutes=sum(v > capacity for v in values)*5 if capacity is not None else None,
                   excess=max(0,limit_basis-capacity) if complete and verified and scenario.get('model_verified') and capacity is not None else None,
                   status='ready' if eligible else 'needs-review')
        rows.append(row);groups[region].append(row)
    pools = []
    for region,members in sorted(groups.items()):
        capacity = scenario.get('pools',{}).get(region)
        capacity = float(capacity) if capacity is not None else None
        all_days = sorted({day for s in members for day in s['day_counts']})
        aggregates = [dict(day=day,mbps=sum(s['daily'][day] for s in members)) for day in all_days if all(day in s['daily'] for s in members)]
        determining = max(aggregates,key=lambda d:d['mbps']) if aggregates else None
        complete = all(s['samples']==expected for s in members)
        supported = region in REGIONS and not (model=='enforced-pool' and region in ('China','Vietnam','Morocco'))
        verified = all(s['verified'] and (s['type'].startswith(('SOCKET_','VSOCKET_','IPSEC_','CROSS_CONNECT')) or s['type']=='CLOUD_INTERCONNECT') for s in members)
        allocation = sum(s['capacity'] for s in members) if all(s['capacity'] is not None for s in members) else None
        observed = (determining['mbps'] if determining else None) if model=='bursting-2027' else allocation if model=='enforced-pool' else sum(s['observed'] for s in members)
        ready = complete and supported and verified and model!='classic-p95' and bool(scenario.get('model_verified'))
        required = (determining['mbps'] if determining else None) if model=='bursting-2027' else sum(s['observed'] for s in members)
        recommendation = (rounded(required,headroom,increment) if model=='bursting-2027' else sum(rounded(s['observed'],headroom,increment) for s in members)) if ready and required is not None else None
        if ready and model=='bursting-2027' and region in ('China','Vietnam','Morocco'):
            recommendation=max(recommendation,sum(s['site_limit_recommendation'] or 0 for s in members))
        compared_capacity = allocation if model=='site' else capacity
        cma = scenario.get('cma',{}).get(month,{}).get(region)
        # CMA usage is compared with observed demand, not projected growth.
        unscaled = not any(float(scenario.get('sites',{}).get(s['id'],{}).get('growth',scenario.get('region_growth',{}).get(region,scenario.get('growth',0)))) != 0 for s in members)
        delta = required-float(cma) if cma is not None and complete and unscaled and model=='bursting-2027' and required is not None else None
        pools.append(dict(region=region,capacity=capacity,allocation=allocation,observed=observed,
                          measured=observed if complete and supported else None,recommendation=recommendation,
                          excess=max(0,observed-compared_capacity) if complete and verified and scenario.get('model_verified') and supported and observed is not None and compared_capacity is not None else None,
                          daily=aggregates,excluded_days=len(all_days)-len(aggregates),complete=complete,supported=supported,
                          status='ready' if ready else 'needs-review',enforced_minimum=sum(s['site_limit_recommendation'] or 0 for s in members) if ready and region in ('China','Vietnam','Morocco') else None,determining_day=determining['day'] if determining else None,
                          contributors=[dict(id=s['id'],name=s['name'],mbps=s['daily'][determining['day']]) for s in members] if determining else [],
                          cma=cma,reconciliation_delta=delta))
        if model=='bursting-2027' and region in ('China','Vietnam','Morocco') and pools[-1]['excess'] is not None and allocation is not None:
            pools[-1]['excess']=max(pools[-1]['excess'],max(0,allocation-(capacity or 0)))
    blockers = []
    if not rows: blockers.append('No site observations in this assessment.')
    if any(s['samples']!=expected for s in rows): blockers.append('Incomplete month: final sizing is withheld. Partial site days are excluded from regional P95 aggregates.')
    if not scenario.get('model_verified'): blockers.append('Confirm the selected licensing model against CMA or the proposed agreement.')
    if any(not s['verified'] or s['region'] not in REGIONS or not (s['type'].startswith(('SOCKET_','VSOCKET_','IPSEC_','CROSS_CONNECT')) or s['type']=='CLOUD_INTERCONNECT') for s in rows): blockers.append('Verify each site region, connection type and inventory assumptions.')
    if any(not p['supported'] for p in pools): blockers.append('The selected model is not supported for one or more regions. No recommendation is produced there.')
    if model=='classic-p95': blockers.append('Classic monthly P95 is an educational comparison; it cannot produce a Cato licensing recommendation.')
    if any(p['reconciliation_delta'] is not None and abs(p['reconciliation_delta'])>max(.5,float(p['cma'])*.01) for p in pools):
        blockers.append('CMA reconciliation exceeds tolerance; resolve the difference before final sizing.')
        for p in pools:p['recommendation']=None;p['status']='needs-review'
        for s in rows:s['recommendation']=None;s['site_limit_recommendation']=None;s['status']='needs-review'
    warnings=[]
    if model=='bursting-2027': warnings.append('Migration scenario: January 2027 bursting model, October 4, 2026 calculation profile.')
    if any(s['constrained'] for s in rows): warnings.append('Enforced traffic may hide unmet demand. Review per-site limits separately from pool measurement.')
    if any(s['zero_buckets'] for s in rows): warnings.append('Zero-valued telemetry is present; confirm whether it represents idle traffic or unavailable telemetry.')
    if any(p['reconciliation_delta'] is not None and abs(p['reconciliation_delta'])>.5 for p in pools): warnings.append('Modeled usage differs from the supplied CMA result. Resolve the discrepancy before using the assessment commercially.')
    ready = bool(rows) and not blockers
    return dict(month=month,model=model,profile=PROFILE,source=SOURCE,sites=rows,pools=pools,
                warnings=blockers+warnings,blockers=blockers,ready=ready,
                series=[dict(ts=ts,mbps=v) for ts,v in sorted(trend.items())] if include_series else [],
                peak=max(trend.values(),default=0),total_recommended=sum(p['recommendation'] for p in pools) if ready else None,
                complete=bool(rows) and all(s['samples']==expected for s in rows))


def longest_gap(timestamps,start,end):
    stamps=sorted(set(timestamps))
    if not stamps:return (end-start)//60
    intervals=[stamps[0]-start,end-stamps[-1]-300]+[b-a-300 for a,b in zip(stamps,stamps[1:])]
    return max(intervals,default=0)//60


def inspect_day(sites,samples,scenario,month,sid,day):
    row=next((s for s in sites if str(s['id'])==str(sid)),None)
    if not row:raise ValueError('Unknown site')
    stamp=int(datetime.strptime(day,'%Y-%m-%d').replace(tzinfo=timezone.utc).timestamp())
    if not month_bounds(month)[0]<=stamp<month_bounds(month)[1]:raise ValueError('Day outside month')
    override=scenario.get('sites',{}).get(str(sid),{})
    region=override.get('region',row.get('region','Unassigned'))
    growth=1+float(override.get('growth',scenario.get('region_growth',{}).get(region,scenario.get('growth',0))))/100
    values=sorted([(max(s['up'],s['down'])*growth,s['ts']) for s in samples if str(s['site_id'])==str(sid) and stamp<=s['ts']<stamp+86400])
    cut=len(values)-math.floor(len(values)*.05)
    return dict(day=day,site=row['name'],complete=len(values)==288,p95=p95([v for v,t in values]),
                excluded=len(values)-cut,buckets=[dict(mbps=v,ts=t,excluded=i>=cut) for i,(v,t) in enumerate(values)])
