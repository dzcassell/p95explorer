import csv
import io
import json
import math
import os
import random
import secrets
import threading
import time
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse, parse_qs

from app import store
from app.analytics import analyze, month_bounds, REGIONS, MODELS
from app.cato import Cato
from app.assessment import scenario_valid, number, saved, save_named, history, bundle, import_bundle
from app.analytics import inspect_day
from app.report import pdf_report

STATIC = Path(__file__).parent / 'static'
JOB = {'state':'idle', 'completed':0, 'total':0}
LOCK = threading.Lock()
CSRF = secrets.token_urlsafe(32)


def demo(month):
    start, end = month_bounds(month)
    rng = random.Random(95)
    sites = [dict(id=str(i+1), name=name, region=region, capacity=cap, type='SOCKET_X1500',source='synthetic-demo') for i,(name,region,cap) in enumerate([
        ('New York HQ','Group 1',200), ('London Office','Group 1',100), ('Frankfurt DC','Group 1',300),
        ('Singapore Hub','Group 2',150), ('Sydney Office','Group 2',100), ('Shanghai Office','China',50)])]
    rows = []
    for ts in range(start, end, 300):
        dt = datetime.fromtimestamp(ts, timezone.utc)
        for i,s in enumerate(sites):
            local_hour = (dt.hour + [-4,1,2,8,10,8][i]) % 24
            work = 1 if 8 <= local_hour <= 18 and dt.weekday() < 5 else .28
            base = [120,60,210,100,65,35][i] * work * (1 + .12 * math.sin(dt.day/4))
            v = base * rng.uniform(.7,1.2)
            if rng.random() < .025:
                v *= rng.uniform(2.1,3.2)
            if i == 2 and dt.day in (12,13):
                v *= 1.65
            rows.append(dict(site_id=s['id'],ts=ts,up=v * rng.uniform(.25,.85),down=v))
    store.save('demo', sites, rows)


def credentials(body):
    return Cato(body.get('account') or os.environ.get('CATO_ACCOUNT_ID',''),
                body.get('key') or os.environ.get('CATO_API_KEY',''),
                body.get('endpoint') or os.environ.get('CATO_API_ENDPOINT','https://api.catonetworks.com/api/v1/graphql2'))


def run_sync(client, site_ids, start, end):
    try:
        tenant = str(client.account)
        discovered = {str(s['id']): s for s in client.discover()}
        if any(str(s) not in discovered for s in site_ids):
            raise ValueError('Selected site not returned by Cato discovery')
        sites = [dict(id=str(s), name=discovered[str(s)]['name'], source='cato-api', type=discovered[str(s)].get('info',{}).get('connType','Unknown')) for s in site_ids]
        store.save(tenant, sites, [])
        def progress(done, total):
            with LOCK:
                JOB.update(completed=done,total=total)
        client.collect(site_ids, start, end, progress, lambda rows: store.save(tenant, [], rows))
        store.setting('active_tenant', tenant)
        with LOCK:
            JOB.update(state='done')
    except Exception as error:
        with LOCK:
            JOB.update(state='error', error=str(error) if isinstance(error, ValueError) else 'Collection failed; inspect connectivity and try again. Saved buckets are retained.')


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *_):
        pass  # Never log requests that can contain tenant information.

    def respond(self, value, status=200, kind='application/json'):
        data = json.dumps(value, allow_nan=False).encode() if kind == 'application/json' else value if isinstance(value,bytes) else value.encode()
        self.send_response(status)
        self.send_header('Content-Type', kind + '; charset=utf-8')
        self.send_header('Content-Length',str(len(data)))
        self.send_header('Cache-Control','no-store')
        self.send_header('X-Content-Type-Options','nosniff')
        self.send_header('Content-Security-Policy', "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'")
        self.end_headers()
        self.wfile.write(data)

    def allowed_host(self):
        host = self.headers.get('Host', '').split(':')[0]
        return host in ('localhost', '127.0.0.1')

    def do_GET(self):
        if not self.allowed_host():
            return self.respond({'error':'Use localhost or 127.0.0.1 to access this local app'},403)
        parsed = urlparse(self.path)
        if parsed.path == '/api/health':
            return self.respond({'status':'ok'})
        if parsed.path == '/api/state':
            tenant = store.setting('active_tenant') or 'demo'
            with LOCK:
                job = dict(JOB)
            return self.respond(dict(tenant=tenant, months=store.months(tenant), job=job,
                scenario=store.setting('scenario:'+tenant), scenarios=saved(tenant), csrf=CSRF,
                endpoint=os.environ.get('CATO_API_ENDPOINT','https://api.catonetworks.com/api/v1/graphql2'),
                env_configured=bool(os.environ.get('CATO_API_KEY') and os.environ.get('CATO_ACCOUNT_ID'))))
        if parsed.path == '/api/assessment':
            tenant=store.setting('active_tenant') or 'demo'
            try:return self.respond(bundle(tenant))
            except ValueError:return self.respond({'error':'Assessment exceeds portable size limit. Use selected-month CSV exports or a full volume backup.'},413)
        if parsed.path == '/api/export':
            tenant = store.setting('active_tenant') or 'demo'
            month = parse_qs(parsed.query).get('month',[''])[0]
            try:
                start,end = month_bounds(month)
                sites,samples = store.dataset(tenant,start,end)
                names = {s['id']:s for s in sites}
                out = io.StringIO()
                writer = csv.writer(out)
                writer.writerow(['site_id','name','region','timestamp','up_mbps','down_mbps'])
                for s in samples:
                    site = names[s['site_id']]
                    name = site['name']
                    if name.startswith(('=','+','-','@','\t','\r')):
                        name = "'" + name
                    writer.writerow([s['site_id'],name,site['region'],datetime.fromtimestamp(s['ts'], timezone.utc).isoformat(),s['up'],s['down']])
                return self.respond(out.getvalue(),kind='text/csv')
            except ValueError:
                return self.respond({'error':'Invalid month'},400)
        names = {'/':'index.html','/app.js':'app.js','/style.css':'style.css'}
        if parsed.path in names:
            kind = {'/':'text/html','/app.js':'text/javascript','/style.css':'text/css'}[parsed.path]
            return self.respond((STATIC/names[parsed.path]).read_text(),kind=kind)
        self.respond({'error':'Not found'},404)

    def do_POST(self):
        if not self.allowed_host():
            return self.respond({'error':'Use localhost or 127.0.0.1 to access this local app'},403)
        try:
            if self.headers.get('X-P95-CSRF') != CSRF:
                return self.respond({'error':'Refresh the page before submitting'},403)
            origin = self.headers.get('Origin')
            if origin and urlparse(origin).netloc != self.headers.get('Host'):
                return self.respond({'error':'Cross-origin request refused'},403)
            size = int(self.headers.get('Content-Length','0'))
            if not 0 < size <= (64_000_000 if self.path == '/api/assessment/import' else 12_000_000):
                return self.respond({'error':'Request exceeds size limit'},413)
            body = json.loads(self.rfile.read(size))
            tenant = store.setting('active_tenant') or 'demo'
            if self.path == '/api/analyze':
                start,end = month_bounds(body['month'])
                sites,samples = store.dataset(tenant,start,end)
                result = analyze(sites,samples,body['month'],scenario_valid(body.get('scenario',{})))
                return self.respond(result)
            if self.path == '/api/history':
                return self.respond(history(tenant,body['months'],scenario_valid(body['scenario'])))
            if self.path == '/api/compare':
                scenarios=saved(tenant)
                identifiers=body['ids']
                if not identifiers or len(identifiers)>4 or any(i not in scenarios for i in identifiers):
                    raise ValueError('Select up to four saved scenarios')
                return self.respond({'results':[dict(id=i,assessment=history(tenant,body['months'],scenario_valid(scenarios[i]))) for i in identifiers]})
            if self.path == '/api/scenarios/save':
                return self.respond({'id':save_named(tenant,body['scenario'],body.get('id'))})
            if self.path == '/api/day':
                start,end=month_bounds(body['month']);sites,samples=store.dataset(tenant,start,end)
                return self.respond(inspect_day(sites,samples,scenario_valid(body['scenario']),body['month'],body['site'],body['day']))
            if self.path == '/api/report':
                scenario=scenario_valid(body['scenario'])
                return self.respond(pdf_report(tenant,scenario,history(tenant,body['months'],scenario)),kind='application/pdf')
            if self.path == '/api/assessment/import':
                with LOCK:
                    if JOB['state']=='running':return self.respond({'error':'Wait for active collection before restoring an assessment'},409)
                return self.respond({'tenant':import_bundle(body)})
            if self.path == '/api/scenario':
                value = scenario_valid(body['scenario'])
                store.setting('scenario:'+tenant,value)
                # Persist verified region/limit edits so CSV exports retain mapping.
                with store.connect() as db:
                    for sid,s in value.get('sites',{}).items():
                        db.execute('UPDATE sites SET region=?,capacity=? WHERE tenant=? AND id=?', (s['region'],s['capacity'],tenant,sid))
                return self.respond({'saved':True})
            if self.path == '/api/demo':
                with LOCK:
                    if JOB['state'] == 'running':
                        return self.respond({'error':'Wait for the active collection to finish'},409)
                month = body.get('month') or datetime.now(timezone.utc).strftime('%Y-%m')
                from app.assessment import next_month
                count=int(number(body.get('months',3),1,12))
                for offset in range(count):demo(next_month(month,-offset))
                if not (store.setting('scenario:demo') or {}).get('model_verified'):
                    start,end=month_bounds(month);sites,_=store.dataset('demo',start,end)
                    store.setting('scenario:demo',scenario_valid(dict(name='Demo baseline',model='bursting-2027',model_verified=True,pools={'Group 1':500,'Group 2':300,'China':80},sites={s['id']:dict(region=s['region'],capacity=s['capacity'],type=s['type'],verified=True) for s in sites})))
                store.setting('active_tenant','demo')
                return self.respond({'month':month})
            if self.path == '/api/discover':
                client = credentials(body)
                sites = client.discover()
                # Country and type help the user exclude VPN users and verify regions.
                return self.respond({'sites':sites,'account':str(client.account)})
            if self.path == '/api/sync':
                client = credentials(body)
                start,_ = month_bounds(body.get('start_month',body['month']))
                _,end = month_bounds(body['month'])
                if end<=start or end-start>366*86400:raise ValueError('Select up to 12 months in chronological order')
                # No future bucket requests; collect through the last completed UTC day.
                end = min(end, int(time.time()) // 86400 * 86400)
                if end <= start:
                    raise ValueError('Choose a month with at least one completed UTC day')
                ids = body['site_ids']
                if not ids or len(ids) > 1000 or any(not str(s).isdigit() for s in ids):
                    raise ValueError('Select 1–1000 numeric site IDs')
                with LOCK:
                    if JOB['state'] == 'running':
                        return self.respond({'error':'A collection is already running'},409)
                    JOB.clear()
                    JOB.update(state='running', completed=0, total=0)
                threading.Thread(target=run_sync,args=(client,ids,start,end),daemon=True).start()
                return self.respond({'started':True},202)
            if self.path == '/api/import':
                with LOCK:
                    if JOB['state'] == 'running':
                        return self.respond({'error':'Wait for collection before importing a dataset'},409)
                tenant = str(body.get('tenant','imported'))
                if not tenant or len(tenant) > 100 or tenant == 'demo':
                    raise ValueError('Use a distinct tenant label, other than demo')
                reader = csv.DictReader(io.StringIO(body['csv']))
                required = {'site_id','name','region','timestamp','up_mbps','down_mbps'}
                if not required.issubset(reader.fieldnames or []):
                    raise ValueError('CSV requires '+', '.join(sorted(required)))
                sites, samples, seen = {}, [], set()
                for row in reader:
                    sid = row['site_id']
                    if not sid.isdigit():
                        raise ValueError('Site IDs must be numeric')
                    if row['region'] not in REGIONS + ('Unassigned',):
                        raise ValueError('Invalid CSV region')
                    dt = datetime.fromisoformat(row['timestamp'].replace('Z','+00:00'))
                    if dt.tzinfo is None:
                        raise ValueError('CSV timestamps must include a timezone')
                    ts = int(dt.timestamp())
                    if ts % 300 or dt.microsecond:
                        raise ValueError('CSV samples must align to five-minute UTC boundaries')
                    if (sid,ts) in seen:
                        raise ValueError('Duplicate CSV bucket')
                    seen.add((sid,ts))
                    sites[sid] = dict(id=sid,name=row['name'],region=row['region'])
                    samples.append(dict(site_id=sid,ts=ts,up=number(row['up_mbps']),down=number(row['down_mbps'])))
                if not samples:
                    raise ValueError('CSV contains no samples')
                store.save(tenant,list(sites.values()),samples)
                store.setting('active_tenant',tenant)
                return self.respond({'imported':len(samples)})
            return self.respond({'error':'Not found'},404)
        except (ValueError,KeyError,TypeError,OverflowError):
            # ValueError messages are authored by us except JSON/date/float parsers.
            return self.respond({'error':'Invalid input or API request. Check dates, numeric values, CSV format, tenant ID, endpoint and API permissions.'},400)
        except Exception:
            return self.respond({'error':'Request failed. Local data has been retained.'},500)


def main():
    store.connect().close()
    host = os.environ.get('P95_BIND','127.0.0.1')
    port = int(os.environ.get('P95_PORT','8080'))
    print('P95 Explorer listening on %s:%d' % (host,port),flush=True)
    ThreadingHTTPServer((host,port),Handler).serve_forever()


if __name__ == '__main__':
    main()
