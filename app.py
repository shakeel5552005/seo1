import streamlit as st
import requests, re, io, json, time, zipfile, csv, html
from bs4 import BeautifulSoup
from urllib.parse import urlparse, urljoin, urldefrag, parse_qsl, urlencode
from collections import Counter, deque
from datetime import datetime, timezone
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak, KeepTogether
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.units import mm


APP_NAME = "SEO Master Pro – AI Website Auditor"
BRAND = "SA digital marketing"
OWNER = "Designed by Shakeel Ahmed"
EMAIL = "shakeel5552005@gmail.com"
UA = "Mozilla/5.0 (compatible; SADigitalMarketingSEO/2.0; +https://example.com)"
TIMEOUT = 18

st.set_page_config(page_title=APP_NAME, page_icon="🔎", layout="wide", initial_sidebar_state="expanded")
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;500;600;700;800&family=Manrope:wght@600;700;800&display=swap');
html,body,[class*="css"]{font-family:'DM Sans',sans-serif}
.stApp{background:linear-gradient(145deg,#f4f7fc 0%,#edf3fb 55%,#f8fbff 100%)}
.block-container{max-width:1500px;padding-top:1.25rem;padding-bottom:3rem}
.hero{padding:30px 34px;border-radius:22px;color:#fff;background:linear-gradient(115deg,#101a36 0%,#234a91 58%,#087e8b 100%);box-shadow:0 14px 36px #132b501c;margin-bottom:20px}
.hero h1{font-family:Manrope,sans-serif;font-size:2.15rem;font-weight:800;margin:6px 0}.hero p{opacity:.9;margin:5px 0}.brandline{font-size:.78rem;letter-spacing:.12em;text-transform:uppercase;font-weight:700}
.metric{background:#fff;border:1px solid #e3eaf4;border-radius:16px;padding:15px 17px;box-shadow:0 5px 18px #1c35500a;min-height:95px}.metric .v{font-size:1.75rem;font-weight:800;color:#172b50}.metric .k{font-size:.8rem;color:#64748b}
.stTabs [data-baseweb="tab-list"]{gap:8px}.stTabs [data-baseweb="tab"]{background:#e8eef7;border-radius:10px 10px 0 0;padding:10px 16px}
div[data-testid="stExpander"]{background:#fff;border:1px solid #e5ebf4;border-radius:12px}
footer{visibility:hidden}
</style>
""", unsafe_allow_html=True)
st.markdown(f'''<div class="hero"><div class="brandline">{BRAND} · WEBSITE GROWTH TOOLKIT · VERSION 2.0</div><h1>{APP_NAME}</h1><p>Full-site crawling · On-page & technical SEO · Mobile & desktop performance · Google index insights · Detailed reports</p><p style="font-size:.82rem;margin-top:14px">{OWNER} &nbsp;|&nbsp; {EMAIL}</p></div>''', unsafe_allow_html=True)

# ---------- Core helpers ----------
def normalize_url(raw):
    raw=(raw or '').strip()
    if not raw:return ''
    if not re.match(r'^https?://',raw,re.I):raw='https://'+raw
    p=urlparse(raw)
    if not p.netloc:return ''
    return p.geturl()

def host_key(url):return (urlparse(url).hostname or '').lower().removeprefix('www.')
def clean_url(url):
    u,_=urldefrag(url)
    p=urlparse(u)
    # strip common tracking parameters, retain functional query strings
    q=[(k,v) for k,v in parse_qsl(p.query,keep_blank_values=True) if not k.lower().startswith(('utm_','gclid','fbclid'))]
    return p._replace(fragment='',query=urlencode(q,doseq=True)).geturl().rstrip('/') or p.scheme+'://'+p.netloc

def get(url, **kwargs):
    headers=kwargs.pop('headers',{})
    headers.setdefault('User-Agent',UA)
    return requests.get(url,headers=headers,timeout=kwargs.pop('timeout',TIMEOUT),allow_redirects=True,**kwargs)

def text_content(soup):
    s=BeautifulSoup(str(soup),'html.parser')
    for x in s(['script','style','noscript','svg','template']):x.decompose()
    return ' '.join(s.stripped_strings)

def extract_keywords(text,limit=20):
    words=re.findall(r"\b[a-zA-Z][a-zA-Z0-9'-]{2,}\b",(text or '').lower())
    stop=set('the and for with that this from your you are was were have has had not but can our their they them about into also more best quality high good all any one two use using its it s of to in on at by as is be an a or we our if how what when where which who why their these those'.split())
    return Counter(w for w in words if w not in stop and not w.isdigit()).most_common(limit)

def fetch_html(url):
    r=get(url)
    ctype=r.headers.get('content-type','').lower()
    if 'text/html' not in ctype and not r.text.lstrip().lower().startswith(('<!doctype html','<html')):
        raise ValueError(f"Not an HTML page (content-type: {ctype or 'unknown'})")
    return r.url,r.text,r.status_code,dict(r.headers)

def parse_robots(base):
    url=urljoin(base,'/robots.txt')
    try:
        r=get(url,timeout=10)
        if r.status_code==200:return r.text
    except Exception:pass
    return ''

def robots_allows(path,robots_text):
    # Conservative, basic robots.txt parser for wildcard user-agent rules.
    active=False; disallows=[]; allows=[]
    for raw in robots_text.splitlines():
        line=raw.split('#',1)[0].strip()
        if not line or ':' not in line:continue
        k,v=[x.strip() for x in line.split(':',1)];k=k.lower()
        if k=='user-agent':
            if active and (disallows or allows):break
            active=(v=='*');disallows=[];allows=[]
        elif active and k=='disallow' and v:disallows.append(v)
        elif active and k=='allow' and v:allows.append(v)
    matches=[(len(x),True) for x in allows if path.startswith(x)]+[(len(x),False) for x in disallows if path.startswith(x)]
    return max(matches)[1] if matches else True

def discover_sitemaps(base,robots_text):
    found=[]
    for line in robots_text.splitlines():
        if line.lower().startswith('sitemap:'):found.append(line.split(':',1)[1].strip())
    found += [urljoin(base,'/sitemap.xml'),urljoin(base,'/sitemap_index.xml')]
    return list(dict.fromkeys(found))

def sitemap_urls(base,robots_text,limit=500):
    urls=[];seen=set();queue=deque(discover_sitemaps(base,robots_text))
    while queue and len(urls)<limit:
        sm=queue.popleft()
        if sm in seen:continue
        seen.add(sm)
        try:
            r=get(sm,timeout=12)
            if r.status_code!=200:continue
            soup=BeautifulSoup(r.content,'xml')
            for loc in soup.find_all('loc'):
                value=loc.get_text(strip=True)
                if soup.find('sitemapindex') and value.lower().endswith('.xml'):queue.append(value)
                elif value and host_key(value)==host_key(base):urls.append(clean_url(value))
        except Exception:continue
    return list(dict.fromkeys(urls))[:limit]

def crawl_site(start_url,max_pages=50,max_depth=3,obey_robots=True,include_query=False):
    base=urlparse(start_url);robots_text=parse_robots(start_url)
    sitemap=sitemap_urls(start_url,robots_text,limit=max_pages*5)
    queue=deque([(start_url,0)]);queued={clean_url(start_url)}
    for u in sitemap:
        if clean_url(u) not in queued:queue.append((u,0));queued.add(clean_url(u))
    visited=set();pages=[];errors=[]
    session=requests.Session();session.headers.update({'User-Agent':UA})
    while queue and len(pages)<max_pages:
        url,depth=queue.popleft();key=clean_url(url)
        if key in visited:continue
        visited.add(key)
        path=urlparse(url).path or '/'
        if obey_robots and not robots_allows(path,robots_text):
            errors.append({'url':url,'error':'Blocked by robots.txt'});continue
        try:
            r=session.get(url,timeout=TIMEOUT,allow_redirects=True)
            ctype=r.headers.get('content-type','').lower()
            if 'text/html' not in ctype:continue
            final=clean_url(r.url)
            if final in {p['url'] for p in pages}:continue
            info=audit_page(final,r.text,r.status_code,dict(r.headers),start_url)
            info['depth']=depth;pages.append(info)
            if depth<max_depth:
                soup=BeautifulSoup(r.text,'html.parser')
                for a in soup.find_all('a',href=True):
                    href=a.get('href','').strip()
                    if not href or href.startswith(('#','mailto:','tel:','javascript:')):continue
                    dest=clean_url(urljoin(r.url,href));p=urlparse(dest)
                    if p.scheme not in ('http','https') or host_key(dest)!=host_key(start_url):continue
                    if not include_query and p.query:continue
                    if re.search(r'\.(pdf|jpg|jpeg|png|gif|webp|svg|zip|docx?|xlsx?|pptx?|mp4|mp3)(\?|$)',p.path,re.I):continue
                    if dest not in queued and dest not in visited:queued.add(dest);queue.append((dest,depth+1))
        except Exception as e:errors.append({'url':url,'error':str(e)[:240]})
        time.sleep(.12)
    return pages,errors,sitemap,robots_text

def audit_page(url,html_text,status,headers,root_url):
    soup=BeautifulSoup(html_text,'html.parser')
    title=soup.title.get_text(' ',strip=True) if soup.title else ''
    md=soup.find('meta',attrs={'name':re.compile('^description$',re.I)})
    desc=(md.get('content') or '').strip() if md else ''
    can=soup.find('link',rel=lambda x:x and 'canonical' in x)
    canonical=urljoin(url,can.get('href','')) if can and can.get('href') else ''
    robots=soup.find('meta',attrs={'name':re.compile('^robots$',re.I)})
    robots_meta=(robots.get('content') or '') if robots else ''
    h1=[x.get_text(' ',strip=True) for x in soup.find_all('h1')]
    h2=[x.get_text(' ',strip=True) for x in soup.find_all('h2')]
    imgs=soup.find_all('img');missing_alt=[x.get('src','(no src)') for x in imgs if not (x.get('alt') or '').strip()]
    host=host_key(root_url);internal=[];external=[]
    for a in soup.find_all('a',href=True):
        d=urljoin(url,a['href']);p=urlparse(d)
        if p.scheme in ('http','https'):
            (internal if host_key(d)==host else external).append(clean_url(d))
    body=text_content(soup);words=re.findall(r"\b[\w'-]+\b",body)
    viewport=soup.find('meta',attrs={'name':re.compile('^viewport$',re.I)})
    lang=soup.html.get('lang','') if soup.html else ''
    schema=soup.find_all('script',attrs={'type':'application/ld+json'})
    ogt=soup.find('meta',property='og:title');ogd=soup.find('meta',property='og:description')
    hcanonical=host_key(canonical)==host if canonical else False
    checks=[]
    def add(name,passed,severity,detail,fix,group='On-page'):
        checks.append({'name':name,'passed':bool(passed),'severity':severity,'detail':str(detail),'fix':fix,'group':group})
    add('HTTPS',urlparse(url).scheme=='https','High','HTTPS enabled' if urlparse(url).scheme=='https' else 'Page is not served over HTTPS.','Install/renew SSL and force HTTP to HTTPS.','Technical')
    add('HTTP status',200<=status<400,'High',f'HTTP {status}', 'Resolve 4xx/5xx errors and redirect obsolete URLs with relevant 301 redirects.','Technical')
    add('Title tag',bool(title),'High',title or 'Missing title tag.','Add one unique, descriptive title for this page.')
    add('Title length',30<=len(title)<=60,'Medium',f'{len(title)} characters','Aim for a concise, descriptive title; roughly 30–60 characters is a guideline.')
    add('Meta description',bool(desc),'High',f'{len(desc)} characters' if desc else 'Missing meta description.','Write a unique description that accurately summarizes the page and encourages clicks.')
    add('Meta description length',120<=len(desc)<=160,'Low',f'{len(desc)} characters','Review the description for clarity and useful detail; length is a guideline.')
    add('Single H1',len(h1)==1,'High',f'{len(h1)} H1 heading(s)','Use one clear primary heading that reflects the page topic.')
    add('H2 structure',len(h2)>0,'Low',f'{len(h2)} H2 heading(s)','Use descriptive subheadings to organize substantial content.')
    add('Image alt text',len(missing_alt)==0,'Medium',f'{len(missing_alt)} of {len(imgs)} images missing alt text','Add meaningful alt text to informative images; use empty alt for decorative images.')
    add('Mobile viewport',viewport is not None,'High','Viewport tag found' if viewport else 'Viewport tag missing.','Add a responsive viewport meta tag.','Technical')
    add('Canonical URL',bool(canonical),'Medium',canonical or 'Missing canonical URL.','Add a correct canonical URL to consolidate duplicate URL signals.','Technical')
    add('Canonical host',not canonical or hcanonical,'Medium',canonical or 'Not applicable', 'Ensure canonical points to the preferred URL on the correct host.','Technical')
    add('Structured data',len(schema)>0,'Low',f'{len(schema)} JSON-LD block(s)','Add relevant, valid Schema.org structured data where appropriate.')
    add('Open Graph',bool(ogt and ogd),'Low','OG title and description found' if ogt and ogd else 'OG title or description missing.','Add og:title and og:description for better social sharing.')
    add('Content length',len(words)>=300,'Medium',f'{len(words)} visible words','Ensure the page provides enough useful information to satisfy its search intent; there is no universal word-count target.')
    add('Internal links',len(internal)>0,'Medium',f'{len(internal)} internal links','Add contextual links to relevant pages and make important pages discoverable.')
    add('Broken/empty links',not any(not a.get('href','').strip() for a in soup.find_all('a')),'Low','No empty hrefs detected' if not any(not a.get('href','').strip() for a in soup.find_all('a')) else 'Empty anchor href detected','Fix empty or placeholder links.')
    add('Indexing directive','noindex' not in robots_meta.lower(),'High',robots_meta or 'No robots meta directive','Remove noindex only if the page is intended to be indexed.','Technical')
    add('Language attribute',bool(lang),'Low',lang or 'HTML lang attribute missing','Set an accurate lang attribute on the HTML element.','Technical')
    add('Favicon',bool(soup.find('link',rel=lambda x:x and 'icon' in x)),'Low','Favicon link found' if soup.find('link',rel=lambda x:x and 'icon' in x) else 'No favicon link detected','Add a favicon link for browser and brand recognition.')
    keywords=extract_keywords(body,20)
    return {'url':url,'status':status,'title':title,'description':desc,'canonical':canonical,'h1':h1,'h2':h2,'images':len(imgs),'missing_alt':missing_alt,'internal':list(dict.fromkeys(internal)),'external':list(dict.fromkeys(external)),'words':len(words),'lang':lang,'schema':len(schema),'checks':checks,'keywords':keywords,'body_text':body[:12000],'headers':headers}

def score_page(page):
    checks=page['checks'];passed=sum(c['passed'] for c in checks)
    return round(100*passed/max(1,len(checks)))

def make_keyword_ideas(pages,seed=''):
    counts=Counter()
    for p in pages:
        for k,n in p['keywords']:counts[k]+=n
    suggestions=[]
    if seed.strip():
        try:
            endpoint='https://suggestqueries.google.com/complete/search'
            r=get(endpoint,params={'client':'firefox','q':seed.strip()},timeout=10)
            if r.ok:
                data=r.json()
                suggestions=[{'keyword':x,'source':'Google Autocomplete','frequency':'Not provided'} for x in data[1][:20]]
        except Exception:pass
    seen={x['keyword'].lower() for x in suggestions}
    for k,n in counts.most_common(30):
        if k not in seen:suggestions.append({'keyword':k,'source':'Website content analysis','frequency':n})
    return suggestions[:40]

def ollama_keyword_ideas(base_url,model,seed,pages):
    sample=[]
    for p in pages[:8]:
        sample.append(f"URL: {p['url']}\nTitle: {p['title']}\nH1: {'; '.join(p['h1'])}\nText: {p['body_text'][:900]}")
    prompt=("Act as an SEO keyword strategist. Suggest 20 realistic target keyword phrases based only on this website context. "
            "Return ONLY valid JSON: {\"keywords\":[{\"keyword\":\"phrase\",\"intent\":\"informational/commercial/transactional/navigational\",\"reason\":\"short reason\"}]}. "
            f"Seed topic: {seed or 'infer from website'}. Website context:\n"+'\n\n'.join(sample))
    r=requests.post(base_url.rstrip('/')+'/api/generate',json={'model':model,'prompt':prompt,'stream':False,'format':'json'},timeout=120)
    r.raise_for_status();raw=r.json().get('response','')
    match=re.search(r'\{.*\}',raw,re.S)
    if not match:raise ValueError('AI response was not valid JSON.')
    data=json.loads(match.group(0));out=[]
    for item in data.get('keywords',[]):
        if item.get('keyword'):out.append({'keyword':item['keyword'],'source':'Ollama AI (local)','intent':item.get('intent','Not classified'),'reason':item.get('reason','')})
    if not out:raise ValueError('No keyword suggestions were returned.')
    return out

def get_psi(url,strategy):
    endpoint='https://www.googleapis.com/pagespeedonline/v5/runPagespeed'
    params={'url':url,'strategy':strategy,'category':['PERFORMANCE','SEO','ACCESSIBILITY','BEST_PRACTICES']}
    r=get(endpoint,params=params,timeout=75);r.raise_for_status();return r.json()

def psi_summary(payload):
    lr=payload.get('lighthouseResult',{});cats=lr.get('categories',{});audits=lr.get('audits',{})
    out={'strategy':lr.get('configSettings',{}).get('formFactor','').title()}
    for k in ['performance','seo','accessibility','best-practices']:
        out[k]=round((cats.get(k,{}).get('score') or 0)*100)
    for k in ['largest-contentful-paint','first-contentful-paint','total-blocking-time','cumulative-layout-shift','speed-index']:
        a=audits.get(k,{})
        out[k]=a.get('displayValue','N/A')
    return out

def report_pdf(pages,errors,psi,keywords,site):
    buf=io.BytesIO();doc=SimpleDocTemplate(buf,pagesize=landscape(A4),rightMargin=12*mm,leftMargin=12*mm,topMargin=12*mm,bottomMargin=13*mm)
    ss=getSampleStyleSheet();ss.add(ParagraphStyle(name='Tiny',parent=ss['BodyText'],fontSize=6.5,leading=8));ss.add(ParagraphStyle(name='SmallHead',parent=ss['Heading2'],fontSize=12,textColor=colors.HexColor('#18356b')));ss.add(ParagraphStyle(name='Cover',parent=ss['Title'],fontSize=22,textColor=colors.HexColor('#18356b'),alignment=TA_CENTER))
    P=lambda x:Paragraph(html.escape(str(x or '—')).replace('\n','<br/>'),ss['Tiny'])
    story=[Paragraph('SEO MASTER PRO · WEBSITE AUDIT',ss['Cover']),Paragraph(f'{BRAND} | {OWNER} | {EMAIL}',ss['Normal']),Spacer(1,8),P(f'Website: {site}'),P(f'Report generated: {datetime.now().strftime("%d %b %Y, %H:%M")}'),Spacer(1,8)]
    avg=round(sum(score_page(p) for p in pages)/max(1,len(pages)))
    allchecks=[c for p in pages for c in p['checks']];fails=sum(not c['passed'] for c in allchecks)
    summary=[['Metric','Result'],['Pages audited',len(pages)],['Average checklist score',f'{avg}/100'],['Total checks',len(allchecks)],['Issues detected',fails],['Crawl errors',len(errors)],['Sitemap URLs discovered',len(st.session_state.get('sitemap_urls',[]))]]
    t=Table([[P(c) for c in row] for row in summary],colWidths=[55*mm,40*mm]);t.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),colors.HexColor('#18356b')),('TEXTCOLOR',(0,0),(-1,0),colors.white),('GRID',(0,0),(-1,-1),.35,colors.HexColor('#cbd5e1')),('ROWBACKGROUNDS',(0,1),(-1,-1),[colors.white,colors.HexColor('#f1f5f9')]),('PADDING',(0,0),(-1,-1),5)]));story += [t,Spacer(1,10),Paragraph('Executive Summary',ss['SmallHead'])]
    priority=Counter(c['name'] for c in allchecks if not c['passed'] and c['severity']=='High')
    story.append(P('Highest-priority recurring issues: '+('; '.join(f'{k} ({v} pages)' for k,v in priority.most_common(10)) if priority else 'No high-priority checklist failures were found.')))
    if psi:
        story += [Spacer(1,8),Paragraph('Google PageSpeed Insights',ss['SmallHead'])]
        rows=[['Device','Performance','SEO','Accessibility','Best Practices','LCP','FCP','TBT','CLS']]
        for device,p in psi.items():
            s=psi_summary(p);rows.append([device.title(),s['performance'],s['seo'],s['accessibility'],s['best-practices'],s['largest-contentful-paint'],s['first-contentful-paint'],s['total-blocking-time'],s['cumulative-layout-shift']])
        tb=Table([[P(x) for x in row] for row in rows],repeatRows=1);tb.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),colors.HexColor('#18356b')),('TEXTCOLOR',(0,0),(-1,0),colors.white),('GRID',(0,0),(-1,-1),.3,colors.HexColor('#cbd5e1')),('PADDING',(0,0),(-1,-1),4)]));story += [tb]
    story += [PageBreak(),Paragraph('All Pages · Crawl Summary',ss['SmallHead'])]
    rows=[['#','Page URL','HTTP','Score','Title','Words','Images missing alt','Internal links','Issues']]
    for i,p in enumerate(pages,1):rows.append([i,p['url'],p['status'],score_page(p),p['title'],p['words'],len(p['missing_alt']),len(p['internal']),sum(not c['passed'] for c in p['checks'])])
    tb=Table([[P(x) if not isinstance(x,(int,float)) else str(x) for x in row] for row in rows],colWidths=[8*mm,78*mm,13*mm,13*mm,48*mm,14*mm,20*mm,18*mm,13*mm],repeatRows=1)
    tb.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),colors.HexColor('#18356b')),('TEXTCOLOR',(0,0),(-1,0),colors.white),('GRID',(0,0),(-1,-1),.25,colors.HexColor('#cbd5e1')),('VALIGN',(0,0),(-1,-1),'TOP'),('ROWBACKGROUNDS',(0,1),(-1,-1),[colors.white,colors.HexColor('#f6f8fc')]),('PADDING',(0,0),(-1,-1),4)]));story.append(tb)
    for i,p in enumerate(pages,1):
        story += [PageBreak(),Paragraph(f'Page {i} · Detailed SEO Audit',ss['SmallHead']),P(p['url']),P(f"HTTP {p['status']} | Checklist score {score_page(p)}/100 | {p['words']} words"),Spacer(1,5)]
        rows=[['Category','Check','Status','Finding','Recommended action']]
        for c in p['checks']:rows.append([P(c['group']),P(c['name']),P('PASS' if c['passed'] else c['severity']+' FIX'),P(c['detail']),P(c['fix'])])
        tb=Table(rows,colWidths=[22*mm,33*mm,20*mm,75*mm,105*mm],repeatRows=1)
        tb.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),colors.HexColor('#18356b')),('TEXTCOLOR',(0,0),(-1,0),colors.white),('GRID',(0,0),(-1,-1),.25,colors.HexColor('#cbd5e1')),('VALIGN',(0,0),(-1,-1),'TOP'),('ROWBACKGROUNDS',(0,1),(-1,-1),[colors.white,colors.HexColor('#f6f8fc')]),('PADDING',(0,0),(-1,-1),4)]));story.append(tb)
        story += [Spacer(1,7),Paragraph('Top keyword ideas from page text',ss['Heading3']),P(', '.join(k for k,n in p['keywords'][:15]) or 'Not enough readable text.')]
    story += [PageBreak(),Paragraph('Keyword Discovery',ss['SmallHead'])]
    for k in keywords[:40]:story.append(P(f"{k['keyword']} | Source: {k['source']} | Frequency: {k.get('frequency','—')}"))
    if errors:
        story += [Spacer(1,8),Paragraph('Crawl Errors / Skipped URLs',ss['SmallHead'])]
        for e in errors[:100]:story.append(P(f"{e['url']} — {e['error']}"))
    story += [Spacer(1,12),P('Methodology note: Scores are an automated checklist indicator, not a Google ranking score. PageSpeed is measured for the homepage only. Backlink authority, search volume, live keyword positions and competitor rankings require external datasets. Indexing status is only verified when Google Search Console URL Inspection is connected; sitemap presence does not prove indexing.')]
    doc.build(story);return buf.getvalue()

def gsc_credentials(service_json_text):
    from google.oauth2 import service_account
    from google.auth.transport.requests import Request
    info=json.loads(service_json_text)
    creds=service_account.Credentials.from_service_account_info(info,scopes=['https://www.googleapis.com/auth/webmasters.readonly'])
    creds.refresh(Request())
    return creds

def gsc_url_inspection(creds,site_url,inspection_url):
    endpoint='https://searchconsole.googleapis.com/v1/urlInspection/index:inspect'
    r=requests.post(endpoint,headers={'Authorization':f'Bearer {creds.token}','Content-Type':'application/json'},json={'inspectionUrl':inspection_url,'siteUrl':site_url,'languageCode':'en-US'},timeout=25)
    r.raise_for_status();return r.json().get('inspectionResult',{})

def gsc_search_analytics(creds,site_url,start_date,end_date):
    endpoint='https://searchconsole.googleapis.com/webmasters/v3/sites/'+requests.utils.quote(site_url,safe='')+'/searchAnalytics/query'
    r=requests.post(endpoint,headers={'Authorization':f'Bearer {creds.token}','Content-Type':'application/json'},json={'startDate':start_date,'endDate':end_date,'dimensions':['query'],'rowLimit':100,'type':'web'},timeout=30)
    r.raise_for_status();return r.json().get('rows',[])

def make_csv(pages):
    out=io.StringIO();fields=['url','status','score','title','description','canonical','words','h1_count','images','missing_alt','internal_links','external_links','failed_checks']
    w=csv.DictWriter(out,fieldnames=fields);w.writeheader()
    for p in pages:w.writerow({'url':p['url'],'status':p['status'],'score':score_page(p),'title':p['title'],'description':p['description'],'canonical':p['canonical'],'words':p['words'],'h1_count':len(p['h1']),'images':p['images'],'missing_alt':len(p['missing_alt']),'internal_links':len(p['internal']),'external_links':len(p['external']),'failed_checks':sum(not c['passed'] for c in p['checks'])})
    return out.getvalue().encode('utf-8-sig')

def make_xlsx(pages):
    try:
        import pandas as pd
        from openpyxl import Workbook
        from openpyxl.styles import Font,PatternFill,Alignment
        from openpyxl.utils import get_column_letter
    except Exception:return None
    from openpyxl import Workbook
    wb=Workbook();ws=wb.active;ws.title='Page Summary'
    headers=['URL','HTTP','SEO Checklist Score','Title','Meta Description','Words','H1 Count','Images','Missing Alt','Internal Links','External Links','Failed Checks']
    ws.append(headers)
    for p in pages:ws.append([p['url'],p['status'],score_page(p),p['title'],p['description'],p['words'],len(p['h1']),p['images'],len(p['missing_alt']),len(p['internal']),len(p['external']),sum(not c['passed'] for c in p['checks'])])
    for c in ws[1]:c.font=Font(bold=True,color='FFFFFF');c.fill=PatternFill('solid',fgColor='18356B')
    ws.freeze_panes='A2';ws.auto_filter.ref=ws.dimensions
    for col in ws.columns:
        width=min(55,max(13,max(len(str(c.value or '')) for c in col)+2));ws.column_dimensions[get_column_letter(col[0].column)].width=width
    detail=wb.create_sheet('All SEO Checks');detail.append(['URL','Score','Category','Check','Status','Finding','Recommended Action'])
    for p in pages:
        for c in p['checks']:detail.append([p['url'],score_page(p),c['group'],c['name'],'PASS' if c['passed'] else 'FIX',c['detail'],c['fix']])
    for c in detail[1]:c.font=Font(bold=True,color='FFFFFF');c.fill=PatternFill('solid',fgColor='18356B')
    detail.freeze_panes='A2';detail.auto_filter.ref=detail.dimensions
    for col in detail.columns:
        width=min(65,max(14,max(len(str(c.value or '')) for c in col)+2));detail.column_dimensions[get_column_letter(col[0].column)].width=width
    b=io.BytesIO();wb.save(b);return b.getvalue()

# ---------- Sidebar controls ----------
with st.sidebar:
    st.markdown('### ⚙️ Audit Settings')
    max_pages=st.slider('Maximum pages to crawl',5,200,50,5)
    max_depth=st.slider('Maximum crawl depth',1,8,3)
    obey=st.checkbox('Respect robots.txt',True)
    include_query=st.checkbox('Include URLs with query strings',False)
    st.caption('Crawling is limited to the same domain. Start with 25–50 pages for larger sites.')
    st.markdown('---')
    st.markdown('**Google Search Console**')
    st.caption('Optional service-account connection for verified index status and search performance. No GSC connection is required for the audit.')
    gsc_upload=st.file_uploader('Service account JSON (optional)',type=['json'],key='gsc_upload_file')
    gsc_property=st.text_input('GSC property URL',placeholder='sc-domain:example.com or https://example.com/',key='gsc_property')
    st.markdown('---')
    st.markdown('**Optional Local AI (Ollama)**')
    ollama_url=st.text_input('Ollama server URL','http://localhost:11434')
    ollama_model=st.text_input('Ollama model','llama3.2:3b')

url_input=st.text_input('Website URL',placeholder='https://example.com')
seed=st.text_input('Seed keyword / service (optional)',placeholder='e.g. BOPP packing tape Pakistan')
col1,col2=st.columns([1,3])
with col1:run=st.button('🚀 Run Full Website Audit',type='primary',use_container_width=True)
with col2:st.caption('Crawls internal pages discovered through links and XML sitemaps. Public HTML pages only; private/admin pages are not accessed.')

if run:
    start=normalize_url(url_input)
    if not start or not urlparse(start).netloc:st.error('Please enter a valid website URL.')
    else:
        try:
            with st.spinner(f'Crawling up to {max_pages} pages and running SEO checks… This may take a few minutes.'):
                pages,errors,sitemaps,robots=crawl_site(start,max_pages,max_depth,obey,include_query)
                if not pages:raise ValueError('No crawlable HTML pages found. Check the URL, robots.txt, or site availability.')
                ideas=make_keyword_ideas(pages,seed)
            st.session_state['pages']=pages;st.session_state['crawl_errors']=errors;st.session_state['sitemap_urls']=sitemaps;st.session_state['keyword_ideas']=ideas;st.session_state['site']=start;st.session_state['psi']={};st.session_state['run_at']=datetime.now().isoformat()
            st.success(f"Audit completed: {len(pages)} pages analyzed.")
        except Exception as e:st.error(f'Audit could not be completed: {e}')

if 'pages' in st.session_state:
    pages=st.session_state['pages'];errors=st.session_state['crawl_errors'];ideas=st.session_state['keyword_ideas'];site=st.session_state['site']
    avg=round(sum(score_page(p) for p in pages)/len(pages));issues=sum(sum(not c['passed'] for c in p['checks']) for p in pages);high=sum(1 for p in pages for c in p['checks'] if not c['passed'] and c['severity']=='High')
    m=st.columns(5)
    for c,v,k in zip(m,[f'{avg}/100',len(pages),issues,high,len(errors)],['Average SEO score','Pages audited','Total issues','High priority issues','Crawl errors']):
        with c:st.markdown(f'<div class="metric"><div class="v">{v}</div><div class="k">{k}</div></div>',unsafe_allow_html=True)
    tabs=st.tabs(['Executive Summary','All Pages','Page Details','Keyword Ideas','PageSpeed','Google Index','Downloads'])
    with tabs[0]:
        st.subheader('Website SEO Executive Summary')
        st.write('**Website:**',site,' | **Audit time:**',st.session_state.get('run_at',''))
        st.progress(avg/100,text=f'Average automated checklist score: {avg}/100 (not a Google ranking score)')
        c1,c2=st.columns(2)
        with c1:
            st.markdown('#### Most common issues')
            freq=Counter(c['name'] for p in pages for c in p['checks'] if not c['passed'])
            if freq:st.dataframe([{'Issue':k,'Affected pages':v} for k,v in freq.most_common(12)],use_container_width=True,hide_index=True)
            else:st.success('No failed checklist checks detected.')
        with c2:
            st.markdown('#### Priority recommendations')
            for issue,count in freq.most_common(8):st.markdown(f'- **{issue}** — review on {count} page(s).')
            st.markdown('- Review high-priority indexing directives and canonical tags.')
            st.markdown('- Improve mobile performance based on PageSpeed diagnostics.')
            st.markdown('- Strengthen internal linking to important commercial pages.')
        st.markdown('#### Crawl coverage')
        st.write(f"Sitemap URLs discovered: **{len(st.session_state.get('sitemap_urls',[]))}** · Crawl errors/skipped: **{len(errors)}**")
        if errors:
            with st.expander('View crawl errors'):
                st.dataframe(errors,use_container_width=True,hide_index=True)
    with tabs[1]:
        rows=[]
        for p in pages:rows.append({'Page URL':p['url'],'HTTP':p['status'],'SEO Score':score_page(p),'Title':p['title'],'Words':p['words'],'H1':len(p['h1']),'Missing Alt':len(p['missing_alt']),'Internal Links':len(p['internal']),'Issues':sum(not c['passed'] for c in p['checks'])})
        st.dataframe(rows,use_container_width=True,hide_index=True)
        st.caption('Select a page in Page Details to inspect its individual checks and recommendations.')
    with tabs[2]:
        labels=[f"{i+1}. {p['url'][:105]}" for i,p in enumerate(pages)]
        idx=st.selectbox('Choose a page',range(len(pages)),format_func=lambda x:labels[x])
        p=pages[idx];ps=score_page(p)
        a,b,c,d=st.columns(4)
        a.metric('Checklist score',f'{ps}/100');b.metric('HTTP status',p['status']);c.metric('Visible words',p['words']);d.metric('Failed checks',sum(not x['passed'] for x in p['checks']))
        st.markdown('**Title:** '+(p['title'] or 'Missing'));st.markdown('**Meta description:** '+(p['description'] or 'Missing'));st.markdown('**Canonical:** '+(p['canonical'] or 'Missing'));st.markdown('**H1:** '+(' · '.join(p['h1']) or 'Missing'))
        for group in ['On-page','Technical']:
            st.markdown(f'#### {group} SEO')
            for x in [x for x in p['checks'] if x['group']==group]:
                with st.expander(('✅ ' if x['passed'] else '⚠️ ')+x['name']+' · '+x['severity']):
                    st.write(x['detail'])
                    if not x['passed']:st.markdown('**Recommended action:** '+x['fix'])
        with st.expander('Internal and external links'):
            st.write('**Internal links**');st.write(p['internal'][:100] or 'None detected');st.write('**External links**');st.write(p['external'][:100] or 'None detected')
        with st.expander('Images missing alt text'):
            st.write(p['missing_alt'][:100] or 'No missing alt text detected.')
    with tabs[3]:
        st.subheader('AI-style Keyword Discovery')
        st.caption('Suggestions combine Google Autocomplete (when reachable) and keyword phrases extracted from crawled website text. Search volume and difficulty are not fabricated.')
        if ideas:st.dataframe(ideas,use_container_width=True,hide_index=True)
        else:st.info('No keyword ideas available. Add a seed keyword and rerun the audit.')
        if st.button('✨ Generate AI Keyword Suggestions with Ollama',key='run_ollama'):
            try:
                with st.spinner('Generating keyword ideas with your local Ollama model…'):
                    ai_ideas=ollama_keyword_ideas(ollama_url,ollama_model,seed,pages)
                st.session_state['ollama_ideas']=ai_ideas
                st.success(f'{len(ai_ideas)} AI keyword ideas generated.')
            except Exception as e:st.error(f'Ollama is not available: {e}. Start Ollama locally and pull the selected model first.')
        if st.session_state.get('ollama_ideas'):
            st.markdown('#### Local AI suggestions')
            st.dataframe(st.session_state['ollama_ideas'],use_container_width=True,hide_index=True)
        st.caption('Google Autocomplete and content-derived ideas work without an AI model. Ollama AI is optional, runs on your own machine, and requires a downloaded local model.')
    with tabs[4]:
        st.subheader('Google PageSpeed Insights · Homepage')
        st.caption('Mobile and desktop Lighthouse tests. PageSpeed may throttle anonymous requests; retry later if Google returns an error.')
        x,y=st.columns(2)
        with x:mobile=st.button('📱 Run Mobile Test')
        with y:desktop=st.button('🖥️ Run Desktop Test')
        if mobile or desktop:
            strategy='mobile' if mobile else 'desktop'
            try:
                with st.spinner(f'Running {strategy} PageSpeed test…'):
                    payload=get_psi(site,strategy);st.session_state['psi'][strategy]=payload
            except Exception as e:st.error(f'PageSpeed request failed: {e}')
        for device,payload in st.session_state.get('psi',{}).items():
            s=psi_summary(payload);st.markdown(f"#### {device.title()} results")
            cc=st.columns(4)
            for col,k in zip(cc,['performance','seo','accessibility','best-practices']):col.metric(k.replace('-',' ').title(),f"{s[k]}/100")
            st.dataframe([{'Metric':k,'Value':s[k]} for k in ['largest-contentful-paint','first-contentful-paint','total-blocking-time','cumulative-layout-shift','speed-index']],use_container_width=True,hide_index=True)
            lr=payload.get('lighthouseResult',{}).get('audits',{})
            with st.expander('Opportunities and diagnostics'):
                for key,audit in lr.items():
                    if audit.get('score') is not None and audit.get('score')<0.9 and audit.get('details',{}).get('type') in ('opportunity','table'):
                        st.write(f"**{audit.get('title')}** — {audit.get('displayValue','Review diagnostic')}")
    with tabs[5]:
        st.subheader('Google Search Index & Ranking')
        st.markdown('**Available without GSC**')
        st.write(f'- Sitemap URLs discovered: {len(st.session_state.get("sitemap_urls",[]))}')
        st.write(f'- Pages crawled by this audit: {len(pages)}')
        st.write('- Page-level noindex directives and canonical URLs are checked.')
        st.markdown('**Optional verified Google data connection**')
        st.caption('Upload a Google Cloud service-account JSON key. Add its client_email as a user with at least Full access to the property in Search Console. The key is used only in this running session and is not written to the report.')
        if gsc_upload and gsc_property.strip():
            try:
                service_text=gsc_upload.getvalue().decode('utf-8')
                if st.button('Connect Google Search Console',key='connect_gsc'):
                    with st.spinner('Authenticating with Google…'):
                        creds=gsc_credentials(service_text)
                    st.session_state['gsc_token']=creds.token
                    st.session_state['gsc_property']=gsc_property.strip()
                    st.session_state['gsc_service_json']=service_text
                    st.success('Google credentials accepted. Property access will be checked when data is requested.')
            except Exception as e:st.error(f'GSC authentication failed: {e}')
        if st.session_state.get('gsc_service_json') and st.session_state.get('gsc_property'):
            st.success(f"GSC property configured: {st.session_state['gsc_property']}")
            import datetime as dt
            date_end=dt.date.today()-dt.timedelta(days=3);date_start=date_end-dt.timedelta(days=27)
            if st.button('Fetch Search Performance (last 28 complete days)',key='gsc_perf'):
                try:
                    with st.spinner('Fetching Google Search Console search queries…'):
                        creds=gsc_credentials(st.session_state['gsc_service_json'])
                        rows=gsc_search_analytics(creds,st.session_state['gsc_property'],date_start.isoformat(),date_end.isoformat())
                    st.session_state['gsc_rows']=rows
                    st.success(f'{len(rows)} query rows returned.')
                except Exception as e:st.error(f'GSC Search Analytics error: {e}')
            if st.session_state.get('gsc_rows') is not None:
                st.dataframe([{'Query':r.get('keys',[''])[0],'Clicks':r.get('clicks',0),'Impressions':r.get('impressions',0),'CTR':f"{r.get('ctr',0)*100:.2f}%",'Avg. Position':round(r.get('position',0),1)} for r in st.session_state['gsc_rows']],use_container_width=True,hide_index=True)
            st.markdown('**Inspect crawled URLs for Google index status**')
            count=st.slider('Number of URLs to inspect (Google quota applies)',1,min(100,len(pages)),min(20,len(pages)),key='gsc_inspect_count')
            if st.button('Inspect URLs in Google Index',key='gsc_inspect'):
                results=[]
                try:
                    with st.spinner('Checking URL Inspection API…'):
                        creds=gsc_credentials(st.session_state['gsc_service_json'])
                        for page in pages[:count]:
                            try:
                                ir=gsc_url_inspection(creds,st.session_state['gsc_property'],page['url'])
                                idx=ir.get('indexStatusResult',{})
                                results.append({'URL':page['url'],'Verdict':idx.get('verdict','Unknown'),'Coverage':idx.get('coverageState',''),'Robots':idx.get('robotsTxtState',''),'Indexing allowed':idx.get('indexingState',''),'Last Crawl':idx.get('lastCrawlTime',''),'Google Canonical':idx.get('googleCanonical','')})
                            except Exception as e:results.append({'URL':page['url'],'Verdict':'Error','Coverage':str(e)[:180]})
                    st.session_state['gsc_index_results']=results
                except Exception as e:st.error(f'URL Inspection failed: {e}')
            if st.session_state.get('gsc_index_results'):
                st.dataframe(st.session_state['gsc_index_results'],use_container_width=True,hide_index=True)
        else:
            st.info('GSC is not connected. Upload a service-account JSON and enter the exact verified property to enable real indexing and search-performance data.')
        st.markdown('**Important:** Sitemap inclusion and `site:` searches do not prove that a URL is indexed. Search Console average position is aggregated performance data, not a guaranteed live rank for every user/location. For independent live SERP checks, a separate SERP provider is required.')
        st.link_button('Open Google Search Console','https://search.google.com/search-console')
    with tabs[6]:
        st.subheader('Download professional SEO reports')
        pdf=report_pdf(pages,errors,st.session_state.get('psi',{}),ideas,site)
        st.download_button('⬇️ Download Detailed PDF Report',pdf,'SA_Digital_Marketing_SEO_Master_Pro_V2_Report.pdf','application/pdf',type='primary')
        st.download_button('⬇️ Download Page Summary CSV',make_csv(pages),'SA_SEO_V2_Page_Summary.csv','text/csv')
        xlsx=make_xlsx(pages)
        if xlsx:st.download_button('⬇️ Download Detailed Excel Report',xlsx,'SA_SEO_V2_Detailed_Report.xlsx','application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
        else:st.info('Excel export requires openpyxl. Install the updated requirements.txt.')
        st.caption('PDF includes executive summary, all-page summary, detailed individual page checks, keyword ideas and available PageSpeed results.')

with st.expander('About this app · Scope & limitations'):
    st.write(f'{BRAND} · {OWNER} · {EMAIL}')
    st.write('Version 2 crawls same-domain public HTML pages discovered via internal links and XML sitemaps. It audits on-page and technical HTML signals and can run Google PageSpeed Insights for the homepage.')
    st.write('Backlink authority, competitor backlink gaps, paid keyword search volume, and verified live SERP rankings need third-party data sources. GSC connection is optional and not yet enabled in this build. Keyword ideas are autocomplete/content-derived rather than guaranteed AI or search-volume data.')
    st.write('Use only on websites you own or are authorized to test. Respect robots.txt and site rate limits.')
st.markdown('---')
st.markdown(f"<div style='text-align:center;color:#718096;font-size:.82rem'>{BRAND} · {OWNER} · {EMAIL} · Version 2.0</div>",unsafe_allow_html=True)
