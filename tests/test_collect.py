import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from scripts.collect_jobs import (
    source_result, reconcile, smartrecruiters, greenhouse, ashby, lever,
    html_jsonld, parse_date, normalized_job, source_result, run
)

SMART = {'id':'clifford-chance-smartrecruiters','firmId':'clifford-chance','company':'Clifford Chance','provider':'smartrecruiters','identifier':'CliffordChance'}
GH = {'id':'testing-greenhouse','firmId':'test','company':'LawFirm','provider':'greenhouse','identifier':'lawfirm'}
ASH = {'id':'testing-ashby','firmId':'test','company':'LawFirm','provider':'ashby','identifier':'lawfirm'}
LEV = {'id':'testing-lever','firmId':'test','company':'LawFirm','provider':'lever','identifier':'lawfirm'}
HTML = {'id':'testing-html','firmId':'test','company':'LawFirm','provider':'html-jsonld','url':'https://lawfirm.example/careers'}

def mock_smart(url, **kwargs):
    if '?limit=' in url:
        return json.dumps({'content':[
            {'id':'100','name':'Middle East Summer Vacation Scheme and Training Contract','location':{'city':'Dubai','country':'AE'},'releasedDate':'2026-10-01T00:00:00Z'},
            {'id':'101','name':'BD Director','location':{'city':'Dubai','country':'AE'}},
            {'id':'102','name':'Paralegal','location':{'city':'New York','country':'US'}}], 'totalFound':3}).encode()
    if url.endswith('/100'):
        return json.dumps({'id':'100','applyUrl':'https://jobs.smartrecruiters.com/CliffordChance/100','applicationDeadline':'2026-11-18',
           'jobAd':{'sections':{'jobDescription':{'text':'Open to graduates; UK-based training.'}}}}).encode()
    raise ValueError('Unexpected URL '+url)

class TestLawCollector(unittest.TestCase):
    def test_smartrecruiters_realistic_feed(self):
        rows, capability=smartrecruiters(SMART,mock_smart)
        self.assertEqual(capability,'verified-feed')
        self.assertEqual(len(rows),1)
        self.assertEqual(rows[0]['id'],'clifford-chance-smartrecruiters:100')
        self.assertEqual(rows[0]['deadline'],'2026-11-18')
        self.assertEqual(rows[0]['level'],'Graduate / early career')

    def test_greenhouse_location_and_role_filter(self):
        def fetch(url,**kw):
            return json.dumps({'jobs':[
                {'id':3,'title':'Corporate Legal Graduate','location':{'name':'Abu Dhabi, UAE'},'absolute_url':'https://boards.greenhouse.io/lawfirm/jobs/3'},
                {'id':4,'title':'Recruiter','location':{'name':'Dubai'},'absolute_url':'https://boards.greenhouse.io/lawfirm/jobs/4'},
                {'id':5,'title':'Paralegal','location':{'name':'London'},'absolute_url':'https://boards.greenhouse.io/lawfirm/jobs/5'}]}).encode()
        jobs,_=greenhouse(GH,fetch)
        self.assertEqual([r['id'] for r in jobs], ['testing-greenhouse:3'])

    def test_ashby_and_lever(self):
        def fa(url,**kw):return json.dumps({'jobs':[{'id':'a1','title':'Junior Legal Counsel','location':'Dubai','jobUrl':'https://jobs.ashbyhq.com/lawfirm/a1','isListed':True},{'id':'a2','title':'Senior IT Director','location':'Dubai','jobUrl':'https://jobs.ashbyhq.com/lawfirm/a2'}]}).encode()
        jobs,_=ashby(ASH,fa)
        self.assertEqual(len(jobs),1)
        def fl(url,**kw):return json.dumps([{'id':'l1','text':'Legal Internship','categories':{'location':'Dubai'},'hostedUrl':'https://jobs.lever.co/lawfirm/l1'}]).encode()
        self.assertEqual(len(lever(LEV,fl)[0]),1)

    def test_html_jsonld_only_not_navigation(self):
        page='''<html><a href="/careers">Apply now</a><script type="application/ld+json">{"@context":"https://schema.org","@type":"JobPosting","identifier":{"value":"xyz"},"title":"Corporate Paralegal","datePosted":"2026-10-29","validThrough":"2026-11-20T00:00:00Z","url":"https://lawfirm.example/jobs/xyz","jobLocation":{"@type":"Place","address":{"addressLocality":"Dubai","addressCountry":"AE"}}}</script></html>'''
        rows, cap=html_jsonld(HTML,lambda url,**kw:page.encode())
        self.assertEqual(cap,'partial-jsonld');self.assertEqual(len(rows),1)
        self.assertEqual(rows[0]['deadline'],'2026-11-20')
        rows,cap=html_jsonld(HTML,lambda url,**kw:b'<html><body><h1>Legal career opportunities and applications</h1><p>Search vacancies on our employment portal.</p><a href="/careers">Jobs here</a></body></html>')
        self.assertEqual(cap,'page-no-job-feed');self.assertEqual(len(rows),0)

    def test_failures_preserve_history_without_false_close(self):
        old={'meta':{'lastSuccessfulAt':'2026-10-01T00:00:00Z'},'jobs':[{'id':'clifford-chance-smartrecruiters:100','sourceId':SMART['id'],'firmId':'clifford-chance','company':'Clifford Chance','title':'Training Contract','url':'https://example.org/job','status':'listed','lastSeenAt':'2026-10-01T00:00:00Z'}]}
        bad={'status':'failed','capability':'unavailable','jobs':[],'message':'403','discovered':0}
        out=reconcile(old,{'sources':[SMART]},[bad],'2026-10-02T00:00:00Z')
        self.assertEqual(out['jobs'][0]['status'],'unverified')
        self.assertEqual(out['meta']['failedSources'],1)
        self.assertEqual(out['events'],[])

    def test_two_successful_misses_required(self):
        old={'meta':{'lastSuccessfulAt':'2026-10-01T00:00:00Z'},'jobs':[{'id':'clifford-chance-smartrecruiters:100','sourceId':SMART['id'],'firmId':'clifford-chance','company':'Clifford Chance','title':'Training Contract','url':'https://example.org/job','status':'listed'}]}
        empty={'status':'ok','capability':'verified-feed','jobs':[],'message':'ok','discovered':0}
        one=reconcile(old,{'sources':[SMART]},[empty],'2026-10-02T00:00:00Z')
        self.assertEqual(one['jobs'][0]['status'],'pending_recheck')
        two=reconcile(one,{'sources':[SMART]},[empty],'2026-10-03T00:00:00Z')
        self.assertEqual(two['jobs'][0]['status'],'not_in_latest_feed')
        self.assertEqual([x['type'] for x in two['events']],['unlisted'])

    def test_new_and_deadline_changes_and_baseline(self):
        job={'id':'clifford-chance-smartrecruiters:100','sourceId':SMART['id'],'firmId':'clifford-chance','company':'Clifford Chance','title':'Training Contract','url':'https://example.org/job','deadline':'2026-11-18','deadlineVerifiedBy':'employer feed'}
        ok={'status':'ok','capability':'verified-feed','jobs':[job],'message':'ok','discovered':1}
        first=reconcile({'meta':{},'jobs':[]},{'sources':[SMART]},[ok],'2026-10-01T00:00:00Z')
        self.assertFalse(first['events'])
        job2=dict(job,deadline='2026-11-21')
        second=reconcile(first,{'sources':[SMART]},[dict(ok,jobs=[job2])],'2026-10-02T00:00:00Z')
        self.assertEqual(second['events'][0]['type'],'deadline_changed')
        new=dict(job,id='clifford-chance-smartrecruiters:102')
        third=reconcile(second,{'sources':[SMART]},[dict(ok,jobs=[job2,new])],'2026-10-03T00:00:00Z')
        self.assertEqual(third['meta']['newRolesLastRun'],1)

    def test_partial_html_never_closes_prior_jobs(self):
        prior={'meta':{'lastSuccessfulAt':'2026-10-01'},'jobs':[{'id':'testing-html:abc','sourceId':'testing-html','company':'LawFirm','title':'Legal Paralegal','url':'https://lawfirm.example/jobs/abc','status':'listed'}]}
        limited={'status':'limited','capability':'page-no-job-feed','jobs':[],'message':'checked','discovered':0}
        out=reconcile(prior,{'sources':[HTML]},[limited],'2026-10-03')
        self.assertEqual(out['jobs'][0]['status'],'unverified')
        self.assertFalse(out['events'])

    def test_invalid_deadline_and_nationality_flag(self):
        self.assertEqual(parse_date('01/01/0001'),'')
        self.assertEqual(parse_date('2026-02-31'),'')
        self.assertEqual(parse_date('2027-03-17T00:00:00Z'),'2027-03-17')
        j=normalized_job(SMART,'xx','Dubai Legal Graduate','Dubai','https://example.org','', '', 'UAE nationals only')
        self.assertEqual(j['eligibilityWarning'],'Nationality restriction indicated')

    def test_full_run_file_writing(self):
        with tempfile.TemporaryDirectory() as td:
            cfg=Path(td)/'config.json';out=Path(td)/'jobs.json'
            cfg.write_text(json.dumps({'sources':[SMART]}))
            x=run(cfg,out,fetcher=mock_smart,timestamp='2026-10-29T08:00:00Z')
            self.assertEqual(x['meta']['verifiedFeedsSuccessful'],1)
            self.assertEqual(len(json.loads(out.read_text())['jobs']),1)

if __name__=='__main__':unittest.main()
