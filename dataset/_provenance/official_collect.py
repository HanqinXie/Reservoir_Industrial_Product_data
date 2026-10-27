from download_official import *
import sys, threading, csv, io, zipfile, calendar
sys.stdout.reconfigure(encoding='utf-8')
LOCK=threading.Lock()
LOG=BASE/'_provenance'/'official_requests.jsonl'
def record(x):
 with LOCK:
  with LOG.open('a',encoding='utf-8') as f:f.write(json.dumps(x,ensure_ascii=False)+'\n')
 return x
def fetch(j):
 i,n,u=j
 try:return record(dict(id=i,**save(i,n,u,'pdf' if n.lower().endswith('.pdf') else None)))
 except Exception as e:return record({'id':i,'url':u,'error':str(e)})
def batch(js):
 with concurrent.futures.ThreadPoolExecutor(5) as ex:
  out=list(ex.map(fetch,js))
 print(json.dumps({'jobs':len(out),'success':sum('error' not in x for x in out),'failed':[x for x in out if 'error' in x]},ensure_ascii=False),flush=True)
 return out

mode=sys.argv[1]
if mode=='water_assets':
 rows=json.loads((BASE/'_provenance'/'water_downloads.json').read_text(encoding='utf-8'))
 jobs=[]
 for row in rows:
  if not row.get('file','').endswith('.html'):continue
  p=BASE/row['file'];s=BeautifulSoup(p.read_bytes(),'html.parser');year=p.name[:4]
  for im in s.select('img[src]'):
   src=im['src']
   if '/material/' in src:continue
   u=urljoin(row['url'],src)
   n=year+'年公报附件/'+u.split('/')[-1].split('?')[0]
   (folder('D14')/(year+'年公报附件')).mkdir(exist_ok=True)
   jobs.append(('D14',n,u));im['src']=n
  (p.with_name(p.stem+'_离线版.html')).write_text(str(s),encoding='utf-8')
 batch(list(dict.fromkeys(jobs)))
elif mode=='shfe':
 jobs=[('D20','上期所_数据接口定义_api.js','https://www.shfe.com.cn/images/api.js')]
 for y in range(2015,2026):jobs.append(('D20',str(y)+'年_期货年度统计.json',f'https://www.shfe.com.cn/data/tradedata/future/yeardata/{y}year.dat'))
 for y in [2022,2023,2024,2025]:
  for m in range(1,13):
   ym=f'{y}{m:02d}'
   jobs.append(('D20',ym+'_期货每月行情.json',f'https://www.shfe.com.cn/data/tradedata/future/monthdata/{ym}month.dat'))
   end=datetime.date(y,m,calendar.monthrange(y,m)[1]);d=end-datetime.timedelta(days=(end.weekday()-4)%7);ds=d.strftime('%Y%m%d')
   jobs.append(('D21',ds+'_铝库存周报.html',f'https://www.shfe.com.cn/data/tradedata/future/stockdata/weeklystock_{ds}/ZH/shfe/al.html'))
 ds='20261026'
 jobs.extend([('D20',ds+'_期货日行情.json',f'https://www.shfe.com.cn/data/tradedata/future/dailydata/kx{ds}.dat'),('D21',ds+'_铝仓单日报.html',f'https://www.shfe.com.cn/data/tradedata/future/stockdata/dailystock_{ds}/ZH/shfe/al.html'),('D21','20261023_铝库存周报.html','https://www.shfe.com.cn/data/tradedata/future/stockdata/weeklystock_20261023/ZH/shfe/al.html')])
 batch(jobs)
elif mode=='stats_rules':
 ls,r=links('https://stats.yn.gov.cn/zwgk/zfxxgk/fdzdgknr/tjsj/tjgb/index.html')
 jobs=[]
 for t,u in ls:
  if re.search(r'云南省20\d{2}年国民经济和社会发展统计公报',t) and 'stats.yn.gov.cn' in u:jobs.append(('D16',t+'.html',u))
 ls,r=links('https://ynb.nea.gov.cn/xxgk/zcfg/')
 for t,u in ls:
  if any(x in t for x in ['市场','交易','并网','供电','售电']) and '/20' in u:
   jobs.append(('D22',re.sub(r'[<>:"/\\|?*]','_',t)[:140]+'.html',u))
 out=batch(list(dict.fromkeys(jobs)))
 attachments=[]
 for row in out:
  if 'error' in row:continue
  p=BASE/row['file'];ls,r=links(row['url'])
  for t,u in ls:
   if re.search(r'\.(pdf|docx?|xlsx?)$',u,re.I):attachments.append((row['id'],re.sub(r'[<>:"/\\|?*]','_',t or u.split('/')[-1])[:160],u))
 batch(list(dict.fromkeys(attachments)))
elif mode=='iai_probe':
 us=['http://international-aluminium.org/statistics/primary-aluminium-smelting-energy-intensity/','http://archive.international-aluminium.org/statistics/primary-aluminium-smelting-energy-intensity/','https://international-aluminium.org/wp-json/wp/v2/statistics','https://archive.international-aluminium.org/wp-json/wp/v2/statistics']
 def f(u):
  try:
   r=requests.get(u,timeout=20);return record({'id':'D17' if 'intensity' in u else 'D18','url':u,'http_status':r.status_code,'bytes':len(r.content),'head':r.text[:100]})
  except Exception as e:return record({'id':'D17','url':u,'error':str(e)})
 with concurrent.futures.ThreadPoolExecutor(4) as ex:
  for x in ex.map(f,us):print(json.dumps(x,ensure_ascii=False),flush=True)
elif mode=='stock_old':
 rows=[json.loads(l) for l in LOG.read_text(encoding='utf-8').splitlines()]
 jobs=[]
 for row in rows:
  if row.get('id')=='D21' and 'error' in row:
   m=re.search(r'weeklystock_(\d{8})',row['url'])
   if m:
    ds=m[1];jobs.append(('D21',ds+'_库存周报_原始数据.json',f'https://www.shfe.com.cn/data/tradedata/future/weeklydata/{ds}weeklystock.dat'))
 batch(list(dict.fromkeys(jobs)))
