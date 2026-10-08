"""Validated scenarios, portable assessments, history and commercial projections."""
import math
import uuid
from datetime import datetime, timezone
from app import store
from app.analytics import analyze, month_bounds, REGIONS, MODELS, rounded, PROFILE


def number(value,low=0,high=1_000_000):
    value=float(value)
    if not math.isfinite(value) or not low<=value<=high:raise ValueError('Numeric value out of range')
    return value


def label(value,limit=160):
    if not isinstance(value,str) or not value.strip() or len(value)>limit:raise ValueError('Invalid text field')
    return value.strip()


def scenario_valid(raw):
    if not isinstance(raw,dict):raise ValueError('Scenario must be an object')
    model=raw.get('model','site')
    if model not in MODELS:raise ValueError('Unknown model')
    if raw.get('horizon') is not None and number(raw['horizon'],1,60)%1:raise ValueError('Horizon must be a whole number')
    s=dict(name=label(raw.get('name','Working scenario')),model=model,
           model_verified=raw.get('model_verified') is True,growth=number(raw.get('growth',0),-90,1000),
           headroom=number(raw.get('headroom',20),0,200),increment=number(raw.get('increment',10),1,10000),
           monthly_growth=number(raw.get('monthly_growth',0),0,30),horizon=int(number(raw.get('horizon',12),1,60)),
           pools={},sites={},region_growth={},cma={},planned_sites=[],commercial={})
    months=raw.get('months',[])
    if not isinstance(months,list) or len(months)>24 or len(set(months))!=len(months):raise ValueError('Invalid observation window')
    for month in months:month_bounds(month)
    s['months']=months
    for region,capacity in raw.get('pools',{}).items():
        if region not in REGIONS+('Unassigned',):raise ValueError('Unknown region')
        s['pools'][region]=number(capacity) if capacity is not None else None
    for region,value in raw.get('region_growth',{}).items():
        if region not in REGIONS:raise ValueError('Unknown growth region')
        s['region_growth'][region]=number(value,-90,1000)
    if len(raw.get('sites',{}))>1000:raise ValueError('Too many site overrides')
    for sid,site in raw.get('sites',{}).items():
        if not str(sid).isdigit():raise ValueError('Invalid site ID')
        region=site.get('region','Unassigned')
        if region not in REGIONS+('Unassigned',):raise ValueError('Unknown site region')
        item=dict(region=region,capacity=number(site['capacity']) if site.get('capacity') is not None else None,
                  type=label(site.get('type','Unknown'),60),enforced=site.get('enforced') is True,verified=site.get('verified') is True)
        if 'growth' in site and site['growth'] is not None:item['growth']=number(site['growth'],-90,1000)
        s['sites'][str(sid)]=item
    for month,groups in raw.get('cma',{}).items():
        month_bounds(month)
        s['cma'][month]={r:number(v) for r,v in groups.items() if r in REGIONS and v is not None}
    if len(raw.get('planned_sites',[]))>100:raise ValueError('Too many planned sites')
    for site in raw.get('planned_sites',[]):
        if site['region'] not in REGIONS:raise ValueError('Unknown planned site region')
        month_bounds(site['start'])
        s['planned_sites'].append(dict(name=label(site['name']),region=site['region'],start=site['start'],
                                      peak=number(site['peak']),p95=number(site['p95'])))
        if s['planned_sites'][-1]['p95']>s['planned_sites'][-1]['peak']:raise ValueError('Planned P95 exceeds peak')
    c=raw.get('commercial',{})
    s['commercial']=dict(currency=label(c.get('currency','USD'),12),flat_monthly=number(c.get('flat_monthly',0)),
                          expansion_fee=number(c.get('expansion_fee',0)),rates={},overage_rates={},
                          verified=c.get('verified') is True,discount=number(c.get('discount',0),0,100),catalog={})
    for field in ('rates','overage_rates'):
        for r,v in c.get(field,{}).items():
            if r not in REGIONS:raise ValueError('Unknown pricing region')
            if v is not None:s['commercial'][field][r]=number(v)
    for region,tiers in c.get('catalog',{}).items():
        if region not in REGIONS or not isinstance(tiers,list) or len(tiers)>50:raise ValueError('Invalid SKU catalog')
        s['commercial']['catalog'][region]=[dict(sku=label(t['sku']),capacity=number(t['capacity'],1),monthly=number(t['monthly'])) for t in tiers]
    return s


def saved(tenant):
    return store.setting('scenarios:'+tenant) or {}


def save_named(tenant,raw,identifier=None):
    scenarios=saved(tenant)
    if identifier and identifier not in scenarios:raise ValueError('Unknown scenario')
    if not identifier and len(scenarios)>=12:raise ValueError('Maximum 12 named scenarios')
    identifier=identifier or str(uuid.uuid4())
    scenarios[identifier]=scenario_valid(raw)
    store.setting('scenarios:'+tenant,scenarios)
    return identifier


def next_month(month,offset=1):
    year,m=map(int,month.split('-'));index=year*12+m-1+offset
    return '%04d-%02d'%(index//12,index%12+1)


def history(tenant,months,scenario):
    if not months or len(months)>24 or len(set(months))!=len(months):raise ValueError('Select 1-24 distinct months')
    months=sorted(months)
    reports=[]
    for month in months:
        start,end=month_bounds(month);sites,samples=store.dataset(tenant,start,end)
        reports.append(analyze(sites,samples,month,scenario,False))
    ready=all(r['ready'] for r in reports)
    if scenario['model']=='enforced-pool' and any(s['region'] in ('China','Vietnam','Morocco') for s in scenario['planned_sites']):ready=False
    region_names=sorted({p['region'] for r in reports for p in r['pools']})
    regional=[]
    for region in region_names:
        matches=[(r,next((p for p in r['pools'] if p['region']==region),None)) for r in reports]
        worst=max([(r,p) for r,p in matches if p and p['recommendation'] is not None],key=lambda v:v[1]['recommendation'],default=None)
        regional.append(dict(region=region,recommendation=worst[1]['recommendation'] if ready and worst else None,
                             determining_month=worst[0]['month'] if worst else None,
                             months_above=sum(p['excess']>0 for r,p in matches if p and p['excess'] is not None),
                             tested_months=sum(p is not None and p['excess'] is not None for r,p in matches)))
    forecast=[]
    forecast_start=max(next_month(months[-1]),'2027-01') if scenario['model']=='bursting-2027' else next_month(months[-1])
    for offset in range(1,scenario.get('horizon',12)+1):
        month=next_month(forecast_start,offset-1);regions=[]
        for region in region_names:
            # Plan from the largest eligible historical requirement, not allocations.
            bases=[]
            for r in reports:
                pool=next((p for p in r['pools'] if p['region']==region),None)
                if pool:
                    value=pool['observed'] if scenario['model']=='bursting-2027' else sum(s['observed'] for s in r['sites'] if s['region']==region)
                    if value is not None:bases.append(value)
            demand=max(bases,default=0)*(1+scenario.get('monthly_growth',0)/100)**offset
            additions=[s for s in scenario.get('planned_sites',[]) if s['region']==region and s['start']<=month]
            demand+=sum(s['p95'] if scenario['model']=='bursting-2027' else s['peak'] for s in additions)
            site_plan=None
            if ready and (scenario['model'] in ('site','enforced-pool') or region in ('China','Vietnam','Morocco')):
                ids={s['id'] for r in reports for s in r['sites'] if s['region']==region}
                site_plan=sum(rounded(max(s['peak'] if region in ('China','Vietnam','Morocco') else s['observed'] for r in reports for s in r['sites'] if s['id']==sid and s['region']==region)*(1+scenario.get('monthly_growth',0)/100)**offset,1+scenario['headroom']/100,scenario['increment']) for sid in ids)
                site_plan+=sum(rounded(s['peak'],1+scenario['headroom']/100,scenario['increment']) for s in additions)
            regions.append(dict(region=region,demand=demand,recommendation=(max(site_plan,rounded(demand,1+scenario['headroom']/100,scenario['increment'])) if site_plan is not None else rounded(demand,1+scenario['headroom']/100,scenario['increment'])) if ready else None,
                                additions=[s['name'] for s in additions]))
        # New regional footprints are explicit assumptions and cannot inherit readiness.
        for region in sorted({s['region'] for s in scenario.get('planned_sites',[])}-set(region_names)):
            additions=[s for s in scenario['planned_sites'] if s['region']==region and s['start']<=month]
            demand=sum(s['p95'] if scenario['model']=='bursting-2027' else s['peak'] for s in additions)
            site_plan=None
            if ready and (scenario['model'] in ('site','enforced-pool') or region in ('China','Vietnam','Morocco')):
                ids={s['id'] for r in reports for s in r['sites'] if s['region']==region}
                site_plan=sum(rounded(max(s['peak'] if region in ('China','Vietnam','Morocco') else s['observed'] for r in reports for s in r['sites'] if s['id']==sid and s['region']==region)*(1+scenario.get('monthly_growth',0)/100)**offset,1+scenario['headroom']/100,scenario['increment']) for sid in ids)
                site_plan+=sum(rounded(s['peak'],1+scenario['headroom']/100,scenario['increment']) for s in additions)
            regions.append(dict(region=region,demand=demand,recommendation=(max(site_plan,rounded(demand,1+scenario['headroom']/100,scenario['increment'])) if site_plan is not None else rounded(demand,1+scenario['headroom']/100,scenario['increment'])) if ready else None,additions=[s['name'] for s in additions]))
        site_capacity=[]
        for sid in sorted({s['id'] for r in reports for s in r['sites']}):
            records=[s for r in reports for s in r['sites'] if s['id']==sid]
            region=records[-1]['region'];demand=max(s['peak'] for s in records)*(1+scenario['monthly_growth']/100)**offset
            site_capacity.append(dict(id=sid,name=records[-1]['name'],region=region,capacity=rounded(demand,1+scenario['headroom']/100,scenario['increment'])))
        for index,s in enumerate(scenario['planned_sites']):
            if s['start']<=month:site_capacity.append(dict(id='planned-'+str(index),name=s['name'],region=s['region'],capacity=rounded(s['peak'],1+scenario['headroom']/100,scenario['increment'])))
        forecast.append(dict(month=month,regions=regions,site_capacity=site_capacity))
    commercial=costs(reports,forecast,scenario,ready)
    return dict(name=scenario['name'],months=reports,regions=regional,ready=ready,forecast=forecast,commercial=commercial,
                assumptions=['Forecast uses the highest observed historical demand with scenario growth, monthly compounded growth, and user-entered planned-site P95/peak budgets.',
                             'Monthly growth compounds during the forecast horizon only. Bursting forecasts start no earlier than January 2027. Forecast is a deterministic planning assumption, not a statistical probability or guaranteed future demand.',
                             'Procurement must confirm regional/site eligibility, actual SKUs, constraints and commercial terms.'])


def costs(reports,forecast,scenario,ready):
    c=scenario['commercial'];regions={p['region'] for f in forecast for p in f['regions']}
    missing=sorted(r for r in regions if r not in c['rates'] and not c.get('catalog',{}).get(r))
    if not c['verified'] or missing or not ready:
        return dict(available=False,reason='Confirm pricing, supply a unit rate or eligible SKU catalog for every region, and resolve assessment blockers.',missing_rates=missing)
    discount=1-c.get('discount',0)/100
    def quote(region,required):
        tiers=c.get('catalog',{}).get(region,[])
        if tiers:
            candidates=[t for t in tiers if t['capacity']>=required]
            if not candidates:raise ValueError('No supplied SKU covers '+region+' capacity')
            chosen=min(candidates,key=lambda t:(t['monthly'],t['capacity']))
            return dict(region=region,required=required,capacity=chosen['capacity'],sku=chosen['sku'],monthly=chosen['monthly']*discount)
        return dict(region=region,required=required,capacity=required,sku='User unit rate',monthly=required*c['rates'][region]*discount)
    monthly=[]
    try:
        for f in forecast:
            items=[dict(quote(s['region'],s['capacity']),site=s['name']) for s in f['site_capacity']] if scenario['model']=='site' else [quote(p['region'],p['recommendation']) for p in f['regions']]
            capacity={r:sum(i['capacity'] for i in items if i['region']==r) for r in regions}
            monthly.append(dict(month=f['month'],amount=round(c['flat_monthly']+sum(i['monthly'] for i in items),2),capacity=capacity,items=items))
        if scenario['model']=='site':
            # Every site's proposed tier stays distinct; no transfer of unused capacity.
            site_names={(s['id'],s['name'],s['region']) for f in forecast for s in f['site_capacity']}
            forward=[dict(quote(r,max(max(s['capacity'] for f in forecast for s in f['site_capacity'] if (s['id'],s['region'])==(sid,r)),next((s['capacity'] or 0 for s in reports[-1]['sites'] if s['id']==sid),0))),site=name) for sid,name,r in sorted(site_names)]
        else:
            forward=[quote(r,max(max(p['recommendation'] for f in forecast for p in f['regions'] if p['region']==r),scenario.get('pools',{}).get(r) or 0)) for r in regions]
    except ValueError as error:
        return dict(available=False,reason=str(error),missing_rates=[])
    target={r:sum(i['capacity'] for i in forward if i['region']==r) for r in regions}
    forward_monthly=c['flat_monthly']+sum(i['monthly'] for i in forward)
    current={r:scenario.get('pools',{}).get(r) for r in regions}
    overage_available=scenario['model']=='bursting-2027' and all(r in c['overage_rates'] and current[r] is not None for r in regions)
    enforcement_ok=all(s['capacity'] is not None and s['capacity']>=s['peak']*(1+scenario['monthly_growth']/100)**len(forecast) for s in reports[-1]['sites'] if s['constrained']) and not any(s['region'] in ('China','Vietnam','Morocco') for s in scenario['planned_sites'])
    overage_available=overage_available and enforcement_ok
    true_up=[]
    if overage_available:
        try:
            base=c['flat_monthly']+sum(quote(r,current[r])['monthly'] for r in regions)
            for f in forecast:
                overage=sum(max(0,p['demand']-current[p['region']])*c['overage_rates'][p['region']]*discount for p in f['regions'])
                true_up.append(dict(month=f['month'],amount=round(base+overage,2),overage=round(overage,2)))
        except ValueError:overage_available=False
    return dict(available=True,currency=c['currency'],monthly=monthly,total=round(sum(m['amount'] for m in monthly),2),
                true_forward_total=round(forward_monthly*len(forecast)+c['expansion_fee'],2),target=target,selected_skus=forward,
                true_up_total=round(sum(m['amount'] for m in true_up),2) if overage_available else None,true_up=true_up,true_up_reason='Unavailable if excess terms/current capacities are missing, the model is enforced, or existing site limits cannot support the projected traffic.',
                note='User-supplied prices only. The lowest-priced supplied SKU covering capacity is selected; fixed site SKUs remain separate. Discount applies to bandwidth and excess charges, not flat fees. True-forward starts at the forecast horizon; historical charges are excluded. Monthly capacity changes are illustrative and may not be allowed by the agreement. Not an official quote.')


def bundle(tenant):
    with store.connect() as db:
        sites=[dict(r) for r in db.execute('SELECT * FROM sites WHERE tenant=?',(tenant,))]
        samples=[dict(r) for r in db.execute('SELECT site_id,ts,up,down FROM samples WHERE tenant=? ORDER BY ts',(tenant,))]
    if len(samples)>600000:raise ValueError('Assessment exceeds 600,000 buckets; use CSV for selected months or a full volume backup.')
    # Serialize only the whitelisted schema. No environment or credential settings.
    for s in sites:s.pop('tenant',None)
    return dict(format='p95-assessment',version=1,profile=PROFILE,exported=datetime.now(timezone.utc).isoformat(),
                tenant=tenant,sites=sites,samples=samples,
                scenario=scenario_valid(store.setting('scenario:'+tenant) or {}),
                scenarios={k:scenario_valid(v) for k,v in saved(tenant).items()})


def import_bundle(raw):
    if raw.get('profile')!=PROFILE:raise ValueError('Assessment rule profile differs; use CSV and re-verify assumptions')
    if raw.get('format')!='p95-assessment' or raw.get('version')!=1:raise ValueError('Unsupported assessment format')
    # Restore into a new isolated workspace; never overwrite an existing tenant.
    tenant='assessment-'+uuid.uuid4().hex[:8]
    sites=[];ids=set()
    if not 0<len(raw['sites'])<=1000 or len(raw['samples'])>600000:raise ValueError('Assessment size out of range')
    for item in raw['sites']:
        sid=str(item['id'])
        if not sid.isdigit() or sid in ids:raise ValueError('Invalid site inventory')
        ids.add(sid)
        if item.get('region','Unassigned') not in REGIONS+('Unassigned',):raise ValueError('Invalid region')
        original_source=str(item.get('source','unknown'))
        while original_source.startswith('assessment-import: '):original_source=original_source[19:]
        if original_source not in ('cato-api','synthetic-demo','csv-import','legacy-unverified'):original_source='unknown'
        sites.append(dict(id=sid,name=label(item['name']),region=item.get('region','Unassigned'),
                          capacity=number(item['capacity']) if item.get('capacity') is not None else None,
                          type=label(item.get('type','Unknown'),60),source='assessment-import: '+original_source))
    samples=[];seen=set()
    for item in raw['samples']:
        sid=str(item['site_id']);ts=item['ts']
        if not isinstance(ts,int) or sid not in ids or ts%300 or not 0<=ts<=4102444800 or (sid,ts) in seen:raise ValueError('Invalid or duplicate bucket')
        seen.add((sid,ts));samples.append(dict(site_id=sid,ts=ts,up=number(item['up']),down=number(item['down'])))
    if not samples:raise ValueError('Assessment has no observations')
    scenario=scenario_valid(raw['scenario'])
    if len(raw.get('scenarios',{}))>12:raise ValueError('Too many scenarios')
    scenarios={str(uuid.uuid4()):scenario_valid(v) for v in raw.get('scenarios',{}).values()}
    with store.connect() as db:
        for s in sites:db.execute('INSERT INTO sites VALUES (?,?,?,?,?,?,?)',(tenant,s['id'],s['name'],s['region'],s['capacity'],s['type'],s['source']))
        db.executemany('INSERT INTO samples VALUES (?,?,?,?,?)',[(tenant,s['site_id'],s['ts'],s['up'],s['down']) for s in samples])
        for key,value in [('scenario:'+tenant,scenario),('scenarios:'+tenant,scenarios),('active_tenant',tenant)]:
            import json
            db.execute('INSERT OR REPLACE INTO settings VALUES (?,?)',(key,json.dumps(value)))
    return tenant
