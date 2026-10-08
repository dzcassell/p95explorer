"""Read-only GraphQL client, deliberately restricted to Cato endpoints."""
import json
import math
import re
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ValueError('API redirects are disabled to protect credentials')


def endpoint(value):
    if not re.fullmatch(r'https://api(?:\.[a-z0-9-]+)?\.catonetworks\.com/api/v1/graphql2', value):
        raise ValueError('Use a Cato HTTPS GraphQL endpoint, e.g. https://api.us1.catonetworks.com/api/v1/graphql2')
    return value


class Cato:
    def __init__(self, account, key, url):
        if not str(account).isdigit() or int(account) <= 0:
            raise ValueError('Tenant ID must be a positive integer')
        if not key or '\n' in key or '\r' in key:
            raise ValueError('A valid API key is required')
        self.account, self.key, self.url = int(account), key, endpoint(url)
        self.last_call = 0
        self.opener = urllib.request.build_opener(NoRedirect())

    def query(self, query):
        for attempt in range(5):
            time.sleep(max(0, 4.2 - (time.monotonic() - self.last_call)))
            self.last_call = time.monotonic()
            request = urllib.request.Request(self.url, json.dumps({'query':query}).encode(),
                {'Content-Type':'application/json', 'x-api-key':self.key}, method='POST')
            try:
                with self.opener.open(request, timeout=60) as response:
                    payload = json.load(response)
                if payload.get('errors'):
                    # Do not relay arbitrary server content containing sensitive inputs.
                    if any('rate' in str(e.get('message','')).lower() for e in payload['errors']) and attempt < 4:
                        time.sleep(5 * (attempt + 1))
                        continue
                    raise ValueError('Cato returned GraphQL errors. Check account ID, key permissions and schema compatibility.')
                if not payload.get('data'):
                    raise ValueError('Cato returned no data')
                return payload['data']
            except urllib.error.HTTPError as error:
                if error.code in (429, 500, 502, 503, 504) and attempt < 4:
                    delay = error.headers.get('Retry-After', '')
                    time.sleep(min(60, int(delay)) if delay.isdigit() else 5 * (attempt + 1))
                    continue
                raise ValueError('Cato API HTTP %s. Verify endpoint and read-only key permissions.' % error.code) from None
            except urllib.error.URLError:
                raise ValueError('Cannot reach Cato API; check DNS, connectivity and TLS trust') from None
        raise ValueError('Cato rate limit retries exhausted')

    def discover(self):
        # Site IDs are explicit during collection to exclude remote users.
        data = self.query('{ accountMetrics(accountID:%d timeFrame:"last.PT5M" groupDevices:true groupInterfaces:true) { sites { id name info { countryCode connType } } } }' % self.account)
        return data['accountMetrics']['sites']

    def collect(self, site_ids, start, end, progress, save):
        if not site_ids or any(not str(s).isdigit() for s in site_ids):
            raise ValueError('Select numeric site IDs')
        # Daily windows with two labels and <=100 sites stay below 100,000 items.
        chunks = [site_ids[i:i+100] for i in range(0, len(site_ids), 100)]
        days = math.ceil((end-start)/86400)
        total = days * len(chunks)
        completed = 0
        for day_start in range(start, end, 86400):
            day_end = min(end, day_start + 86400)
            begin = datetime.fromtimestamp(day_start, timezone.utc).strftime('%Y-%m-%d/%H:%M:%S')
            finish = datetime.fromtimestamp(day_end, timezone.utc).strftime('%Y-%m-%d/%H:%M:%S')
            buckets = (day_end - day_start) // 300
            for chunk in chunks:
                query = '{ accountMetrics(accountID:%d timeFrame:"utc.{%s--%s}" groupDevices:true groupInterfaces:true) { granularity sites(siteIDs:[%s]) { id name interfaces { name timeseries(labels:[bytesUpstreamMax bytesDownstreamMax] buckets:%d) { label units data } } } } }' % (self.account, begin, finish, ','.join(map(str,chunk)), buckets)
                data = self.query(query)['accountMetrics']
                if float(data['granularity']) != 300:
                    raise ValueError('Cato returned non-five-minute data. Collection stopped to avoid misleading P95.')
                samples = normalize(data, start=day_start, end=day_end)
                save(samples)
                completed += 1
                progress(completed, total)


def normalize(data, start=None, end=None):
    samples = []
    for site in data.get('sites', []):
        interfaces = site.get('interfaces', [])
        if len(interfaces) != 1:
            raise ValueError('Expected one grouped interface per site; cannot safely sum independent interface peaks')
        metrics = {}
        for series in interfaces[0].get('timeseries', []):
            if series['label'] not in ('bytesUpstreamMax', 'bytesDownstreamMax'):
                continue
            if series.get('units') != 'bytes':
                raise ValueError('Unexpected Cato peak units; expected bytes per second')
            values = {}
            for stamp, value in series['data']:
                if value is None:
                    continue
                ts = int(stamp) // 1000
                rate = float(value) * 8 / 1_000_000
                if ts % 300 or rate < 0 or not math.isfinite(rate):
                    raise ValueError('Invalid bucket timestamp or throughput')
                if (start is None or ts >= start) and (end is None or ts < end):
                    values[ts] = rate
            metrics[series['label']] = values
        up, down = metrics.get('bytesUpstreamMax', {}), metrics.get('bytesDownstreamMax', {})
        for ts in sorted(up.keys() & down.keys()):
            samples.append(dict(site_id=str(site['id']), ts=ts, up=up[ts], down=down[ts]))
    return samples
