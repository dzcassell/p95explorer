import json
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path
from app import store
from app.server import Handler

class ServerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=tempfile.TemporaryDirectory();cls.old=store.DB;store.DB=Path(cls.tmp.name)/'test.sqlite3'
        cls.server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
        cls.thread=threading.Thread(target=cls.server.serve_forever,daemon=True);cls.thread.start()
        cls.base='http://127.0.0.1:'+str(cls.server.server_port)
        cls.csrf=json.load(urllib.request.urlopen(cls.base+'/api/state'))['csrf']

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown();cls.server.server_close();store.DB=cls.old;cls.tmp.cleanup()

    def post(self,path,body,token=True):
        headers={'Content-Type':'application/json'}
        if token:headers['X-P95-CSRF']=self.csrf
        req=urllib.request.Request(self.base+'/api/'+path,json.dumps(body).encode(),headers)
        return json.load(urllib.request.urlopen(req))

    def test_csrf_and_host(self):
        with self.assertRaises(urllib.error.HTTPError) as e:self.post('demo',{'month':'2026-09'},False)
        self.assertEqual(e.exception.code,403)
        req=urllib.request.Request(self.base+'/api/state',headers={'Host':'evil.example'})
        with self.assertRaises(urllib.error.HTTPError) as e:urllib.request.urlopen(req)
        self.assertEqual(e.exception.code,403)

    def test_demo_analysis_save_and_export(self):
        self.post('demo',{'month':'2026-09'})
        r=self.post('analyze',{'month':'2026-09','scenario':{}})
        self.assertEqual(len(r['sites']),6);self.assertTrue(r['complete'])
        self.assertEqual(len(r['series']),30*288)
        self.post('scenario',{'scenario':{'sites':{'1':{'region':'Group 2','capacity':240}}}})
        state=json.load(urllib.request.urlopen(self.base+'/api/state'))
        self.assertNotIn('key',state);self.assertEqual(state['scenario']['sites']['1']['capacity'],240)
        out=urllib.request.urlopen(self.base+'/api/export?month=2026-09').read().decode()
        self.assertTrue(out.startswith('site_id,name,region,timestamp'))
        self.assertIn('New York HQ,Group 2',out)

    def test_csv_import_duplicates_missing_and_roundtrip(self):
        csv='site_id,name,region,timestamp,up_mbps,down_mbps\n1,Branch,Group 1,2026-09-01T00:00:00Z,20,40\n'
        self.assertEqual(self.post('import',{'csv':csv,'tenant':'test'})['imported'],1)
        r=self.post('analyze',{'month':'2026-09','scenario':{}})
        self.assertFalse(r['complete']);self.assertEqual(r['sites'][0]['peak'],40)
        with self.assertRaises(urllib.error.HTTPError):self.post('import',{'csv':csv+csv.splitlines()[1]+'\n','tenant':'test'})
        self.assertEqual(len(store.dataset('test',1788220800,1790812800)[1]),1)

    def test_history_named_comparison_and_pdf_endpoints(self):
        self.post('demo',{'month':'2026-09','months':2})
        state=json.load(urllib.request.urlopen(self.base+'/api/state'))
        scenario=state['scenario']
        h=self.post('history',{'months':['2026-08','2026-09'],'scenario':scenario})
        self.assertTrue(h['ready']);self.assertEqual(len(h['months']),2)
        named=self.post('scenarios/save',{'scenario':scenario})
        result=self.post('compare',{'months':['2026-09'],'ids':[named['id']]})
        self.assertEqual(result['results'][0]['assessment']['name'],scenario['name'])
        req=urllib.request.Request(self.base+'/api/report',json.dumps({'months':['2026-09'],'scenario':scenario}).encode(),{'Content-Type':'application/json','X-P95-CSRF':self.csrf})
        response=urllib.request.urlopen(req)
        self.assertTrue(response.read().startswith(b'%PDF-'))
        self.assertIn('application/pdf',response.headers['Content-Type'])
        data=json.load(urllib.request.urlopen(self.base+'/api/assessment'))
        restored=self.post('assessment/import',data)
        self.assertTrue(restored['tenant'].startswith('assessment-'))
