import unittest
from app.analytics import analyze, p95, month_bounds
from app.cato import normalize, endpoint
from app.server import scenario_valid

class AnalyticsTests(unittest.TestCase):
    def test_daily_p95_burst_boundary(self):
        self.assertEqual(p95([50]*274+[200]*14),50)
        self.assertEqual(p95([50]*273+[200]*15),200)
        self.assertIsNone(p95([]))
        self.assertEqual(p95([3]),3)

    def test_daily_before_pool_aggregation_and_highest_day(self):
        start,_=month_bounds('2026-09')
        sites=[dict(id=str(i),name=str(i),region='Group 1',capacity=100) for i in (1,2)]
        samples=[]
        for day in range(3):
            for i in range(288):
                # Sites peak at different times; sum of site P95s differs from simultaneous P95.
                samples.extend([dict(site_id='1',ts=start+day*86400+i*300,up=10,down=100 if i<144 else 10),
                                dict(site_id='2',ts=start+day*86400+i*300,up=10,down=(200 if day==1 else 100) if i>=144 else 10)])
        r=analyze(sites,samples,'2026-09',{'model':'bursting-2027','pools':{'Group 1':250},'headroom':20})
        self.assertEqual(r['pools'][0]['measured'],300)
        self.assertEqual(r['pools'][0]['recommendation'],360)
        self.assertEqual(r['pools'][0]['excess'],50)
        self.assertFalse(r['complete'])
        self.assertEqual(r['sites'][0]['complete_days'],3)

    def test_missing_buckets_not_zero_and_max_direction(self):
        start,_=month_bounds('2026-02')
        r=analyze([dict(id='1',name='a',region='Group 1',capacity=90)],
                  [dict(site_id='1',ts=start,up=100,down=100)],'2026-02',{})
        self.assertEqual(r['pools'][0]['measured'],100)
        self.assertEqual(r['sites'][0]['over_minutes'],5)
        self.assertFalse(r['pools'][0]['daily'][0]['complete'])
        self.assertTrue(r['warnings'])

    def test_region_separation_and_enforcement(self):
        start,_=month_bounds('2026-09')
        sites=[dict(id='1',name='a',region='Group 1',capacity=100),dict(id='2',name='b',region='China',capacity=200)]
        samples=[dict(site_id='1',ts=start,up=0,down=80),dict(site_id='2',ts=start,up=10,down=150)]
        r=analyze(sites,samples,'2026-09',{'model':'enforced-pool','headroom':20})
        self.assertEqual({p['region']:p['measured'] for p in r['pools']},{'Group 1':100,'China':200})
        self.assertFalse(next(p for p in r['pools'] if p['region']=='China')['supported'])
        self.assertEqual(next(p for p in r['pools'] if p['region']=='Group 1')['recommendation'],100)

    def test_leap_month_and_year_boundary(self):
        a,b=month_bounds('2024-02');self.assertEqual(b-a,29*86400)
        a,b=month_bounds('2026-12');self.assertEqual(b-a,31*86400)

    def test_growth_and_headroom(self):
        start,_=month_bounds('2026-09')
        r=analyze([dict(id='1',name='a',region='Group 1',capacity=90)],
                  [dict(site_id='1',ts=start,up=100,down=20)],'2026-09',{'growth':50,'headroom':20})
        self.assertEqual(r['pools'][0]['measured'],150)
        self.assertEqual(r['pools'][0]['recommendation'],180)

    def test_input_validation(self):
        for s in [{'growth':float('nan')},{'pools':{'Group 1':-1}},{'model':'made-up'}]:
            with self.assertRaises(ValueError):scenario_valid(s)
        for url in ['http://api.catonetworks.com/api/v1/graphql2','https://api.catonetworks.com.evil.com/api/v1/graphql2','https://localhost/api/v1/graphql2']:
            with self.assertRaises(ValueError):endpoint(url)
        self.assertTrue(endpoint('https://api.us1.catonetworks.com/api/v1/graphql2'))

class CatoConversionTests(unittest.TestCase):
    def payload(self, **kw):
        return {'sites':[{'id':'12','interfaces':[{'timeseries':[
            {'label':'bytesUpstreamMax','units':'bytes','data':[[0,12500000],[300000,None]]},
            {'label':'bytesDownstreamMax','units':'bytes','data':[[0,25000000],[300000,5]]}]}]}]}

    def test_peak_is_rate_and_null_is_missing(self):
        samples=normalize(self.payload())
        self.assertEqual(samples,[dict(site_id='12',ts=0,up=100,down=200)])

    def test_reject_independent_interface_peaks(self):
        data=self.payload();data['sites'][0]['interfaces']*=2
        with self.assertRaises(ValueError):normalize(data)

    def test_reject_units_and_nonfinite(self):
        data=self.payload();data['sites'][0]['interfaces'][0]['timeseries'][0]['units']='bits'
        with self.assertRaises(ValueError):normalize(data)
        data=self.payload();data['sites'][0]['interfaces'][0]['timeseries'][0]['data'][0][1]=float('inf')
        with self.assertRaises(ValueError):normalize(data)

class CollectorContractTests(unittest.TestCase):
    def test_daily_windows_site_batching_and_callbacks(self):
        from app.cato import Cato
        client=Cato('12','fixture-only','https://api.catonetworks.com/api/v1/graphql2')
        queries=[]
        def query(q):
            queries.append(q)
            return {'accountMetrics':{'granularity':300,'sites':[]}}
        client.query=query
        progress=[];saved=[]
        start,end=month_bounds('2026-09')
        client.collect(list(range(1,102)),start,start+86400,lambda a,b:progress.append((a,b)),saved.append)
        self.assertEqual(len(queries),2)
        self.assertEqual(progress,[(1,2),(2,2)])
        self.assertIn('buckets:288',queries[0])
        self.assertIn('groupInterfaces:true',queries[0])
        self.assertIn('utc.{2026-09-01/00:00:00--2026-09-02/00:00:00}',queries[0])
        self.assertIn('siteIDs:[101]',queries[1])

    def test_collector_rejects_coarser_history(self):
        from app.cato import Cato
        client=Cato('12','fixture-only','https://api.catonetworks.com/api/v1/graphql2')
        client.query=lambda q:{'accountMetrics':{'granularity':3600,'sites':[]}}
        start,_=month_bounds('2026-09')
        with self.assertRaises(ValueError):
            client.collect([1],start,start+86400,lambda a,b:None,lambda r:None)
