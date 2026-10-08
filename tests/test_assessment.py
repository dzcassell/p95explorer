import json
import tempfile
import unittest
from pathlib import Path
from app import store
from app.analytics import analyze, month_bounds, inspect_day
from app.assessment import scenario_valid, history, bundle, import_bundle, save_named
from app.report import pdf_report

class EvidenceTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.old=store.DB;store.DB=Path(self.tmp.name)/'workspace.db'
        self.sites=[dict(id='1',name='Branch',region='Group 1',capacity=100,type='SOCKET_X1500',source='test-fixture')]
        self.scenario=scenario_valid(dict(name='Baseline',model='bursting-2027',model_verified=True,headroom=20,pools={'Group 1':90},sites={'1':dict(region='Group 1',capacity=100,type='SOCKET_X1500',verified=True)}))
        self.start,self.end=month_bounds('2026-09')
        self.samples=[dict(site_id='1',ts=ts,up=50,down=100) for ts in range(self.start,self.end,300)]
        store.save('test',self.sites,self.samples)

    def tearDown(self):store.DB=self.old;self.tmp.cleanup()

    def test_verified_complete_month_and_site_enforcement(self):
        r=analyze(self.sites,self.samples,'2026-09',self.scenario)
        self.assertTrue(r['ready']);self.assertEqual(r['total_recommended'],120)
        self.assertEqual(r['pools'][0]['excess'],10)
        self.assertIsNone(r['sites'][0]['site_limit_recommendation'])
        self.scenario['sites']['1']['type']='CLOUD_INTERCONNECT'
        r=analyze(self.sites,self.samples,'2026-09',self.scenario)
        self.assertEqual(r['sites'][0]['site_limit_recommendation'],120)

    def test_partial_site_day_excluded_not_zero_filled(self):
        r=analyze(self.sites,self.samples[1:],'2026-09',self.scenario)
        self.assertFalse(r['ready']);self.assertIsNone(r['total_recommended'])
        self.assertEqual(len(r['pools'][0]['daily']),29)
        self.assertEqual(r['pools'][0]['excluded_days'],1)
        self.assertEqual(r['sites'][0]['missing_buckets'],1)
        self.assertEqual(r['sites'][0]['longest_gap_minutes'],5)

    def test_unverified_input_blocks_recommendation(self):
        self.scenario['sites']['1']['verified']=False
        r=analyze(self.sites,self.samples,'2026-09',self.scenario)
        self.assertFalse(r['ready']);self.assertIsNone(r['total_recommended'])
        self.assertIsNone(r['pools'][0]['recommendation'])

    def test_cma_mismatch_blocks_and_growth_disables_reconciliation(self):
        self.scenario['cma']={'2026-09':{'Group 1':80}}
        r=analyze(self.sites,self.samples,'2026-09',self.scenario)
        self.assertEqual(r['pools'][0]['reconciliation_delta'],20)
        self.assertFalse(r['ready']);self.assertIsNone(r['total_recommended'])
        self.scenario['growth']=20
        r=analyze(self.sites,self.samples,'2026-09',self.scenario)
        self.assertIsNone(r['pools'][0]['reconciliation_delta'])
        self.assertTrue(r['ready'])

    def test_scheduled_site_growth_and_costs(self):
        self.scenario.update(horizon=2,monthly_growth=10,planned_sites=[dict(name='New branch',region='Group 1',start='2027-02',p95=20,peak=50)])
        self.scenario['commercial']=dict(currency='USD',flat_monthly=10,expansion_fee=30,rates={'Group 1':2},overage_rates={'Group 1':3},verified=True)
        h=history('test',['2026-09'],self.scenario)
        self.assertEqual(h['forecast'][0]['regions'][0]['recommendation'],140)
        self.assertEqual(h['forecast'][1]['regions'][0]['recommendation'],170)
        self.assertEqual(h['forecast'][0]['regions'][0]['additions'],[])
        self.assertEqual(h['forecast'][1]['regions'][0]['additions'],['New branch'])
        self.assertEqual(h['commercial']['total'],640)
        self.assertEqual(h['commercial']['true_forward_total'],730)
        self.assertEqual(h['commercial']['true_up_total'],593)

    def test_fixed_sites_round_individually(self):
        self.scenario['model']='site';self.scenario['headroom']=0
        second=dict(id='2',name='Second',region='Group 1',capacity=100,type='SOCKET_X1500')
        samples=[dict(site_id='2',ts=ts,up=0,down=11) for ts in range(self.start,self.end,300)]
        store.save('test',[second],samples)
        self.scenario['sites']['2']=dict(region='Group 1',capacity=100,type='SOCKET_X1500',verified=True)
        h=history('test',['2026-09'],self.scenario)
        self.assertEqual(h['forecast'][0]['regions'][0]['recommendation'],120)

    def test_unsupported_pool_cannot_recommend(self):
        self.scenario['model']='enforced-pool';self.scenario['sites']['1']['region']='China'
        r=analyze(self.sites,self.samples,'2026-09',self.scenario)
        self.assertFalse(r['ready']);self.assertFalse(r['pools'][0]['supported'])
        self.assertIsNone(r['sites'][0]['recommendation'])

    def test_portable_roundtrip_isolated_and_credentials_excluded(self):
        self.scenario['key']='secret-fixture';self.scenario['commercial']['token']='secret-fixture'
        store.setting('scenario:test',self.scenario);save_named('test',self.scenario)
        data=bundle('test')
        self.assertNotIn('secret-fixture',json.dumps(data))
        tenant=import_bundle(data)
        self.assertNotEqual(tenant,'test')
        self.assertEqual(len(store.dataset(tenant,self.start,self.end)[1]),len(self.samples))
        self.assertTrue(history(tenant,['2026-09'],scenario_valid(data['scenario']))['ready'])
        self.assertEqual(store.setting('active_tenant'),tenant)

    def test_bad_bundle_is_atomic(self):
        store.setting('active_tenant','test');store.setting('scenario:test',self.scenario)
        data=bundle('test');data['samples'].append(data['samples'][0])
        with self.assertRaises(ValueError):import_bundle(data)
        self.assertEqual(store.setting('active_tenant'),'test')
        with store.connect() as db:self.assertEqual(db.execute('SELECT COUNT(DISTINCT tenant) FROM sites').fetchone()[0],1)

    def test_explanation_discarded_buckets(self):
        rows=[dict(site_id='1',ts=self.start+i*300,up=0,down=200 if i>=274 else 50) for i in range(288)]
        d=inspect_day(self.sites,rows,self.scenario,'2026-09','1','2026-09-01')
        self.assertTrue(d['complete']);self.assertEqual(d['p95'],50)
        self.assertEqual(sum(b['excluded'] for b in d['buckets']),14)

    def test_pdf_signature_and_report_sections(self):
        h=history('test',['2026-09'],self.scenario)
        data=pdf_report('test',self.scenario,h)
        self.assertTrue(data.startswith(b'%PDF-'))
        self.assertGreater(len(data),4000)

    def test_country_pool_sizing_covers_fixed_site_limits(self):
        self.scenario['sites']['1']['region']='China';self.scenario['pools']={'China':90}
        # P95 is 100 but short spikes reach 200 and must be supported by the enforced site limit.
        samples=[dict(s,down=200 if (s['ts']-self.start)//300%288<10 else 100) for s in self.samples]
        r=analyze(self.sites,samples,'2026-09',self.scenario)
        self.assertEqual(r['pools'][0]['measured'],100)
        self.assertEqual(r['sites'][0]['site_limit_recommendation'],240)
        self.assertEqual(r['pools'][0]['recommendation'],240)

    def test_old_workspace_migration_preserves_observations(self):
        import sqlite3
        other=Path(self.tmp.name)/'legacy.db'
        db=sqlite3.connect(other)
        db.execute('CREATE TABLE sites (tenant TEXT,id TEXT,name TEXT,region TEXT,capacity REAL,type TEXT,PRIMARY KEY(tenant,id))')
        db.execute("INSERT INTO sites VALUES ('old','1','Old branch','Group 1',100,'SOCKET_X1500')")
        db.commit();db.close()
        store.DB=other
        with store.connect() as db:
            row=dict(db.execute('SELECT * FROM sites').fetchone())
            self.assertEqual(row['source'],'legacy-unverified');self.assertEqual(row['capacity'],100)
        store.DB=Path(self.tmp.name)/'workspace.db'

    def test_sku_pricing_discount_and_unavailable_tier(self):
        self.scenario['commercial'].update(verified=True,discount=10,catalog={'Group 1':[dict(sku='100M',capacity=100,monthly=100),dict(sku='200M',capacity=200,monthly=150)]})
        h=history('test',['2026-09'],self.scenario)
        self.assertEqual(h['commercial']['selected_skus'][0]['sku'],'200M')
        self.assertEqual(h['commercial']['total'],135*12)
        self.scenario['commercial']['catalog']['Group 1']=[dict(sku='100M',capacity=100,monthly=100)]
        self.assertFalse(history('test',['2026-09'],self.scenario)['commercial']['available'])

    def test_fixed_site_catalog_does_not_merge_duplicate_names(self):
        self.scenario['model']='site'
        second=dict(id='2',name='Branch',region='Group 1',capacity=100,type='SOCKET_X1500')
        samples=[dict(site_id='2',ts=ts,up=0,down=100) for ts in range(self.start,self.end,300)]
        store.save('test',[second],samples)
        self.scenario['sites']['2']=dict(region='Group 1',capacity=100,type='SOCKET_X1500',verified=True)
        self.scenario['commercial'].update(verified=True,catalog={'Group 1':[dict(sku='200M',capacity=200,monthly=150)]})
        h=history('test',['2026-09'],self.scenario)
        self.assertEqual(len(h['commercial']['selected_skus']),2)
        self.assertEqual(h['commercial']['true_forward_total'],300*12)

    def test_remote_user_type_cannot_be_confirmed_as_site(self):
        self.scenario['sites']['1']['type']='SDP_USER'
        r=analyze(self.sites,self.samples,'2026-09',self.scenario)
        self.assertFalse(r['ready']);self.assertIsNone(r['total_recommended'])

    def test_true_forward_preserves_larger_existing_pool(self):
        self.scenario['pools']['Group 1']=500
        self.scenario['commercial'].update(verified=True,rates={'Group 1':2})
        h=history('test',['2026-09'],self.scenario)
        self.assertEqual(h['commercial']['target']['Group 1'],500)
        self.assertEqual(h['commercial']['true_forward_total'],12000)

    def test_overage_cannot_bypass_site_enforcement(self):
        self.scenario['sites']['1']['enforced']=True
        self.scenario['sites']['1']['capacity']=50
        self.scenario['commercial'].update(verified=True,rates={'Group 1':2},overage_rates={'Group 1':3})
        h=history('test',['2026-09'],self.scenario)
        self.assertIsNone(h['commercial']['true_up_total'])
