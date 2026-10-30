"""Law Career Atlas: conservative, job-level vacancy reconciliation.

Structured public feeds are authoritative for their own advertised listings. Generic
career pages are only used when they expose schema.org JobPosting records; a
changed page or a successful HTML request is NOT evidence of new vacancies.

No login, robots bypass, CAPTCHA bypass, or invented job/deadline is attempted.
"""
from __future__ import annotations

import concurrent.futures
import hashlib
import html
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
USER_AGENT = 'LawCareerAtlas/2.0 (public law firm vacancy checker; GitHub Actions)'
MAX_BYTES = 3_000_000
VALID_UAE = re.compile(r'\b(dubai|abu dhabi|united arab emirates|\buae\b|difc|middle east|\bgcc\b)\b', re.I)
EXCLUDE_GEO = re.compile(r'\b(saudi arabia|riyadh|jeddah|london|new york|singapore|paris|hong kong|bahrain)\b', re.I)
LEGAL_TITLES = re.compile(r'\b(lawyer|legal|paralegal|trainee|training contract|vacation scheme|solicitor|associate|intern|graduate|clerk|insight|corporate|counsel|compliance|projects|finance|arbitration|litigation|funds)\b', re.I)
EXCLUDE_TITLES = re.compile(r'\b(marketing|sales|business development|receptionist|secretary|facilities|human resources|\bhr\b|accountant|it support|driver|office manager|recruiter)\b', re.I)
SENIOR_TITLES = re.compile(r'\b(senior|principal|partner|director|head of|managing|mid.level|\b[4-9]\+?\s*(?:years|yrs|pqe)\b|\b[4-9]\s*[-–]\s*\d+\s*(?:years|yrs|pqe))\b', re.I)
NATIONAL_ONLY = re.compile(r'\b(uae nationals? only|emirati nationals? only|reserved for (?:uae nationals?|emiratis)|emiratisation only|emiratization only|saudi nationals? only)\b', re.I)
GOOD_URL = re.compile(r'^https://', re.I)


def now_utc():
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace('+00:00', 'Z')


def save_json(path: Path, data: dict):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2, sort_keys=False)+'\n', encoding='utf-8')


def http_fetch(url: str, accept='application/json', timeout=17) -> bytes:
    if not GOOD_URL.match(url):
        raise ValueError('Only HTTPS employer sites are supported')
    req = urllib.request.Request(url, headers={'User-Agent': USER_AGENT, 'Accept': accept})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        # urllib follows HTTPS redirects; disallow exceptionally large feeds.
        raw = resp.read(MAX_BYTES+1)
        if len(raw) > MAX_BYTES:
            raise ValueError('Source response is too large')
        return raw


def parse_date(value: Any) -> str:
    if value is None:
        return ''
    s = str(value).strip()
    if isinstance(value,(int,float)) and value>1000000000:
        try:
            epoch=float(value)/(1000 if float(value)>100000000000 else 1)
            d=datetime.fromtimestamp(epoch,timezone.utc).date()
            return d.isoformat() if 2000<=d.year<=2100 else ''
        except (ValueError,OverflowError,OSError):pass
    if not s or s.startswith('0001'):
        return ''
    m = re.search(r'\b(20\d{2})-(\d{2})-(\d{2})(?=$|T|\s|Z)', s)
    if not m:
        return ''
    try:
        return datetime.fromisoformat(m.group(0)).date().isoformat()
    except ValueError:
        return ''


def deadline_from(data: dict) -> str:
    for k in ('applicationDeadline', 'application_deadline', 'validThrough', 'expirationDate', 'closingDate', 'deadline'):
        v = parse_date(data.get(k))
        if v:
            return v
    return ''


def looks_uae(location: str, title: str = '') -> bool:
    text = (location or '').strip()
    if VALID_UAE.search(text):
        return True
    # For an empty location we require an explicit UAE reference in title.
    return not text and bool(VALID_UAE.search(title))


def level(title: str) -> str:
    if SENIOR_TITLES.search(title):
        return 'Experienced / qualified'
    if re.search(r'\b(intern|graduate|trainee|vacation|training contract|paralegal|assistant|junior|insight|newly qualified|nq)\b', title, re.I):
        return 'Graduate / early career'
    return 'Eligibility to verify'


def role_type(title: str) -> str:
    if re.search(r'vacation scheme', title, re.I):
        return 'Vacation scheme'
    if re.search(r'training contract|trainee solicitor', title, re.I):
        return 'Training contract'
    if re.search(r'paralegal|legal assistant', title, re.I):
        return 'Paralegal / legal support'
    if re.search(r'intern|insight', title, re.I):
        return 'Internship / insight'
    if re.search(r'graduate|junior', title, re.I):
        return 'Graduate / junior'
    return 'Legal role'


def relevant(title: str, location: str, source: dict, description='') -> tuple[bool, str]:
    if not looks_uae(location, title):
        return False, 'location outside UAE / Middle East'
    if EXCLUDE_TITLES.search(title):
        return False, 'non-legal support function'
    if not LEGAL_TITLES.search(title):
        return False, 'title not clearly relevant to law'
    return True, ('Nationality restriction indicated' if NATIONAL_ONLY.search(title+' '+description) else '')


def normalized_job(source: dict, jobid: str, title: str, location: str, url: str,
                   posted='', deadline='', description='', confidence='structured-feed') -> dict | None:
    if not GOOD_URL.match(url):
        return None
    ok, warning = relevant(title, location, source, description)
    if not ok:
        return None
    return {
        'id': f"{source['id']}:{jobid}", 'sourceId': source['id'],
        'firmId': source['firmId'], 'company': source['company'],
        'title': title.strip(), 'location': location.strip(),
        'url': url.strip(), 'type': role_type(title), 'level': level(title),
        'postedDate': parse_date(posted), 'deadline': parse_date(deadline),
        'deadlineVerifiedBy': 'employer feed' if parse_date(deadline) else '',
        'eligibilityWarning': warning, 'confidence': confidence,
        'provider': source['provider'],
    }


def smartrecruiters(source: dict, fetcher=http_fetch):
    """Retrieve all published company postings with safe pagination."""
    company = source['identifier']
    records = []
    offset = 0
    limit = 100
    while offset < 1500:
        url = f'https://api.smartrecruiters.com/v1/companies/{urllib.parse.quote(company)}/postings?limit={limit}&offset={offset}'
        page = json.loads(fetcher(url).decode('utf-8'))
        items = page.get('content')
        if not isinstance(items, list):
            raise ValueError('SmartRecruiters returned no postings array')
        for x in items:
            ident = str(x.get('id') or x.get('uuid') or '')
            loc = x.get('location') or {}
            city = str(loc.get('city') or '')
            country = str(loc.get('country') or '')
            if country.strip().upper() in ('AE','ARE'):
                country='UAE'
            region = str(loc.get('region') or '')
            location = ', '.join(v for v in (city, region, country) if v)
            # Accept country code AE (not only the phrase UAE).
            if country.strip().lower() not in ('ae', 'are', 'united arab emirates') and not looks_uae(location, x.get('name','')):
                continue
            title = str(x.get('name') or '')
            if EXCLUDE_TITLES.search(title) or not LEGAL_TITLES.search(title):
                continue
            detail_url = f'https://api.smartrecruiters.com/v1/companies/{urllib.parse.quote(company)}/postings/{urllib.parse.quote(ident)}'
            try:
                details = json.loads(fetcher(detail_url).decode('utf-8'))
            except Exception:
                details = x  # a detail failure is not allowed to discard a listed job
            sections = ((details.get('jobAd') or {}).get('sections') or {})
            desc = ' '.join(html.unescape(str(z.get('text',''))) for z in sections.values() if isinstance(z, dict))
            link = details.get('applyUrl') or f'https://jobs.smartrecruiters.com/{company}/{ident}'
            # Do not derive deadlines from free-text phrases; only explicit official fields.
            job = normalized_job(source, ident, title, location, link,
                                 x.get('releasedDate') or x.get('postedDate'),
                                 deadline_from(details) or deadline_from(x), desc)
            if job:
                records.append(job)
        offset += len(items)
        if len(items) < limit or offset >= int(page.get('totalFound') or offset):
            break
    return records, 'verified-feed'


def greenhouse(source: dict, fetcher=http_fetch):
    url = f"https://boards-api.greenhouse.io/v1/boards/{urllib.parse.quote(source['identifier'])}/jobs?content=true"
    page = json.loads(fetcher(url).decode('utf-8'))
    if not isinstance(page.get('jobs'), list):
        raise ValueError('Greenhouse returned no jobs list')
    records = []
    for x in page['jobs']:
        loc = str((x.get('location') or {}).get('name') or '')
        txt = html.unescape(str(x.get('content') or ''))
        job = normalized_job(source, str(x['id']), str(x.get('title') or ''), loc,
                x.get('absolute_url') or '', x.get('first_published') or x.get('created_at'), deadline_from(x), txt)
        if job:
            records.append(job)
    return records, 'verified-feed'


def ashby(source: dict, fetcher=http_fetch):
    url = f"https://api.ashbyhq.com/posting-api/job-board/{urllib.parse.quote(source['identifier'])}"
    page = json.loads(fetcher(url).decode('utf-8'))
    if not isinstance(page.get('jobs'), list):
        raise ValueError('Ashby returned no jobs list')
    records = []
    for x in page['jobs']:
        if x.get('isListed') is False:
            continue
        locations = [x.get('location') or '']+[v.get('location','') for v in x.get('secondaryLocations',[]) if isinstance(v,dict)]
        loc = next((z for z in locations if looks_uae(z)),locations[0])
        url = x.get('jobUrl') or x.get('applyUrl') or ''
        ident = str(x.get('id') or hashlib.sha256(url.encode()).hexdigest()[:20])
        job = normalized_job(source, ident, str(x.get('title') or ''),str(loc),url,
                         x.get('publishedAt') or x.get('createdAt'),deadline_from(x), x.get('descriptionPlain') or '')
        if job:
            records.append(job)
    return records, 'verified-feed'


def lever(source: dict, fetcher=http_fetch):
    base='https://api.eu.lever.co' if source.get('region')=='eu' else 'https://api.lever.co'
    allitems=[]; skip=0;limit=100
    while skip < 1500:
        url=f"{base}/v0/postings/{urllib.parse.quote(source['identifier'])}?mode=json&limit={limit}&skip={skip}"
        items=json.loads(fetcher(url).decode('utf-8'))
        if not isinstance(items,list):raise ValueError('Lever returned unexpected shape')
        allitems.extend(items)
        skip+=len(items)
        if len(items)<limit:break
    records=[]
    for x in allitems:
        cats=x.get('categories') or {}
        loc=cats.get('location') or ''
        if x.get('workplaceType')=='remote' and not looks_uae(loc):continue
        records.append(normalized_job(source,str(x.get('id') or ''),str(x.get('text') or ''),
                       loc,x.get('hostedUrl') or x.get('applyUrl') or '',
                       x.get('createdAt'),deadline_from(x),x.get('descriptionPlain') or ''))
    return [x for x in records if x], 'verified-feed'


class JSONLDExtractor(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.collect=False
        self.parts=[]
        self.records=[]
    def handle_starttag(self,tag,attrs):
        attrs=dict(attrs)
        if tag=='script' and 'ld+json' in attrs.get('type','').lower():
            self.collect=True;self.parts=[]
    def handle_data(self,data):
        if self.collect:self.parts.append(data)
    def handle_endtag(self,tag):
        if tag=='script' and self.collect:
            self.collect=False
            try:self.records.append(json.loads(''.join(self.parts)))
            except (ValueError,TypeError):pass


def walk_ld(x):
    if isinstance(x, list):
        for v in x:yield from walk_ld(v)
    elif isinstance(x,dict):
        if str(x.get('@type','')).lower().endswith('jobposting') or 'JobPosting' in x.get('@type',[]):
            yield x
        for v in x.get('@graph',[]):yield from walk_ld(v)


def place_name(place):
    if isinstance(place,list):return ' / '.join(place_name(x) for x in place)
    if isinstance(place,str):return place
    if not isinstance(place,dict):return ''
    address=place.get('address') or place.get('applicantLocationRequirements') or {}
    if isinstance(address,str):return address
    if isinstance(address,list):return ' / '.join(place_name(x) for x in address)
    if isinstance(address,dict):
        return ', '.join(str(address.get(k,'')) for k in ('addressLocality','addressRegion','addressCountry') if address.get(k))
    return ''


def html_jsonld(source: dict, fetcher=http_fetch):
    raw=fetcher(source['url'],accept='text/html,application/xhtml+xml;q=0.8')
    text=raw.decode('utf-8',errors='replace')
    if len(text)<80:
        raise ValueError('Empty or incomplete page')
    ex=JSONLDExtractor();ex.feed(text)
    found=list(walk_ld(ex.records))
    records=[]
    for x in found:
        url=x.get('url') or x.get('sameAs') or ''
        if isinstance(url,dict):url=url.get('@id','')
        if isinstance(url,list):url=next((v for v in url if isinstance(v,str)),'')
        url=urllib.parse.urljoin(source['url'],str(url))
        loc=place_name(x.get('jobLocation')) or place_name(x.get('applicantLocationRequirements'))
        title=str(x.get('title') or '')
        ident=str(x.get('identifier',{}).get('value','')) if isinstance(x.get('identifier'),dict) else str(x.get('identifier') or '')
        if not ident:ident=hashlib.sha256(url.encode()).hexdigest()[:20]
        job=normalized_job(source,ident,title,loc,url,
                           x.get('datePosted'),deadline_from(x),
                           x.get('description') or '', confidence='official-page-jsonld')
        if job:records.append(job)
    return records, ('partial-jsonld' if found else 'page-no-job-feed')


PROVIDERS={'smartrecruiters':smartrecruiters,'greenhouse':greenhouse,'ashby':ashby,'lever':lever,'html-jsonld':html_jsonld}


def source_result(source,fetcher=http_fetch):
    try:
        if source['provider'] not in PROVIDERS:raise ValueError('Unsupported provider')
        jobs, capability=PROVIDERS[source['provider']](source,fetcher)
        return {'status':'ok' if capability=='verified-feed' else 'limited',
                'capability':capability,'jobs':jobs,'message':('Company-specific structured jobs feed' if capability=='verified-feed' else 'Career page accessible; only embedded structured JobPosting records can be extracted'),
                'discovered':len(jobs)}
    except Exception as e:
        return {'status':'failed','capability':'unavailable','jobs':[],
                'message':f'{type(e).__name__}: {str(e)[:160]}','discovered':0}


def reconcile(old: dict, config: dict, results: list, timestamp: str) -> dict:
    previous_jobs={x['id']:x for x in old.get('jobs',[])}
    previous_sources={x['id']:x for x in old.get('sources',[])}
    baseline=not old.get('meta',{}).get('lastSuccessfulAt')
    new_jobs={k:dict(v) for k,v in previous_jobs.items()}
    events=[];source_rows=[];feed_success=0;limited_count=0
    for src,res in zip(config['sources'],results):
        prev=previous_sources.get(src['id'],{})
        row={'id':src['id'],'firmId':src['firmId'],'company':src['company'],
             'url':src.get('url') or ('https://careers.smartrecruiters.com/'+src.get('identifier','') if src['provider']=='smartrecruiters' else ''),
             'provider':src['provider'],'status':res['status'],'capability':res['capability'],
             'lastAttemptAt':timestamp,'lastSuccessfulAt':(timestamp if res['status']!='failed' else prev.get('lastSuccessfulAt','')),
             'message':res['message'],'matchingJobs':res['discovered'] if res['status']!='failed' else prev.get('matchingJobs',0)}
        source_rows.append(row)
        if res['status']=='failed':
            # A failed request is not evidence of an open or closed position.
            # Retain historical roles but mark them unverified until a source recovers.
            for ident, historical in previous_jobs.items():
                if historical.get('sourceId')==src['id']:
                    new_jobs[ident]=dict(historical,status='unverified')
            continue
        if res['capability']=='verified-feed':feed_success+=1
        else:limited_count+=1
        seen=set()
        for raw in res['jobs']:
            item=dict(raw); seen.add(item['id'])
            prior=previous_jobs.get(item['id'])
            item.update({'firstSeenAt':prior.get('firstSeenAt',timestamp) if prior else timestamp,
                         'lastSeenAt':timestamp,'missingChecks':0,'status':'listed',
                         'lastSuccessfulSourceAt':timestamp})
            if prior:
                # Do not blank a previously published deadline when a feed omits it today.
                if not item['deadline'] and prior.get('deadline'):
                    item['deadline']=prior['deadline']
                    item['deadlineVerifiedBy']=prior.get('deadlineVerifiedBy','')
                    item['deadlineStatus']='previously published; recheck'
                elif item['deadline'] and prior.get('deadline') and item['deadline']!=prior['deadline']:
                    events.append({'type':'deadline_changed','jobId':item['id'],'company':item['company'],
                                   'title':item['title'],'url':item['url'],'previous':prior['deadline'],
                                   'deadline':item['deadline'],'detectedAt':timestamp})
                else:item['deadlineStatus']='published' if item['deadline'] else 'not published'
            else:
                item['deadlineStatus']='published' if item['deadline'] else 'not published'
                if not baseline:
                    events.append({'type':'new','jobId':item['id'],'company':item['company'],
                                   'title':item['title'],'url':item['url'],'deadline':item['deadline'],
                                   'detectedAt':timestamp})
            new_jobs[item['id']]=item
        # Only a fully enumerated company feed can assert absence of a listing.
        # A partial HTML/JSON-LD career-page check cannot confirm a vacancy's closure.
        if res['capability']=='verified-feed':
            for ident, oldjob in previous_jobs.items():
                if oldjob.get('sourceId')!=src['id'] or ident in seen:
                    continue
                if oldjob.get('status')=='not_in_latest_feed':
                    new_jobs[ident]=oldjob
                    continue
                missing=int(oldjob.get('missingChecks') or 0)+1
                job=dict(oldjob,missingChecks=missing,status=('not_in_latest_feed' if missing>=2 else 'pending_recheck'))
                new_jobs[ident]=job
                if missing==2 and not baseline:
                    events.append({'type':'unlisted','jobId':job['id'],'company':job['company'],
                                   'title':job['title'],'url':job['url'],'detectedAt':timestamp})
        else:
            # HTML schema.org may be incomplete; never mark prior roles unlisted.
            for ident, oldjob in previous_jobs.items():
                if oldjob.get('sourceId')==src['id'] and ident not in seen:
                    new_jobs[ident]=dict(oldjob,status='unverified',missingChecks=0)
    if any(r['status']!='failed' for r in source_rows):last_good=timestamp
    else:last_good=old.get('meta',{}).get('lastSuccessfulAt','')
    meta={'generatedAt':timestamp,'lastAttemptAt':timestamp,'lastSuccessfulAt':last_good,
          'baseline':baseline,'configuredSources':len(source_rows),
          'verifiedFeeds':sum(1 for x in source_rows if x['capability']=='verified-feed'),
          'verifiedFeedsSuccessful':feed_success,'limitedPageChecks':limited_count,
          'failedSources':sum(x['status']=='failed' for x in source_rows),
          'newRolesLastRun':sum(x['type']=='new' for x in events),
          'deadlineChangesLastRun':sum(x['type']=='deadline_changed' for x in events),
          'unlistedLastRun':sum(x['type']=='unlisted' for x in events),
          'sourceCoverage':'Only configured feeds are monitored. No platform can guarantee every vacancy from all firms.'}
    result={'meta':meta,'jobs':sorted(new_jobs.values(),key=lambda x:(x.get('status')!='listed',x.get('company',''),x.get('title',''))),
            'sources':source_rows,'events':events}
    return result


def run(config_path=None, output_path=None, fetcher=http_fetch, timestamp=None):
    config_path=Path(config_path or ROOT/'config/job_sources.json')
    output_path=Path(output_path or ROOT/'data/live_jobs.json')
    cfg=json.loads(config_path.read_text(encoding='utf-8'))
    old=json.loads(output_path.read_text(encoding='utf-8')) if output_path.exists() else {'meta':{},'jobs':[],'sources':[]}
    timestamp=timestamp or now_utc()
    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
        results=list(pool.map(lambda x:source_result(x,fetcher),cfg['sources']))
    out=reconcile(old,cfg,results,timestamp)
    save_json(output_path,out)
    counts=out['meta']
    print(f"Vacancy checks: {counts['verifiedFeedsSuccessful']} structured feeds, {counts['limitedPageChecks']} limited pages, {counts['failedSources']} failed; {len(out['jobs'])} records, {counts['newRolesLastRun']} new")
    return out


if __name__=='__main__':
    run()
