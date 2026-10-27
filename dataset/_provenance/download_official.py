import requests, pathlib, json, hashlib, datetime, re, concurrent.futures
from urllib.parse import urljoin
from bs4 import BeautifulSoup

BASE=pathlib.Path(__file__).resolve().parents[1]
NAMES={
'D14':'云南省水资源公报与官方统计信息','D15':'国家统计局国家数据','D16':'云南省统计局','D17':'IAI原铝冶炼能耗强度','D18':'IAI铝产量与行业统计','D19':'云铝股份年度报告','D20':'上海期货交易所行情数据','D21':'上海期货交易所库存与仓单','D22':'云南能源监管办市场规则与公开运行信息','D23':'南方电网用户账单与计量资料','D29':'水电基础设施REIT招募说明书'}
def folder(i):
 p=BASE/(i+'_'+NAMES[i]);p.mkdir(parents=True,exist_ok=True);return p
def get(url,timeout=70):
 r=requests.get(url,timeout=timeout,headers={'User-Agent':'Mozilla/5.0','Referer':url});r.raise_for_status();return r
def save(i,name,url,expect=None):
 p=folder(i)/name
 if p.exists() and p.stat().st_size>0:return {'file':str(p.relative_to(BASE)),'url':url,'existing':True}
 r=get(url)
 if expect=='pdf' and not r.content.startswith(b'%PDF'):raise ValueError('not PDF '+str(r.headers.get('Content-Type')))
 p.write_bytes(r.content)
 return {'file':str(p.relative_to(BASE)),'url':r.url,'bytes':len(r.content),'content_type':r.headers.get('Content-Type')}
def links(url):
 r=get(url);r.encoding=r.apparent_encoding
 s=BeautifulSoup(r.text,'html.parser')
 return [(a.get_text(' ',strip=True),urljoin(r.url,a['href'])) for a in s.select('a[href]')],r
def inspect(url):
 try:
  ls,r=links(url)
  return {'url':url,'status':r.status_code,'bytes':len(r.content),'title':BeautifulSoup(r.text,'html.parser').title.get_text() if BeautifulSoup(r.text,'html.parser').title else '', 'links':ls}
 except Exception as e:return {'url':url,'error':str(e)}
if __name__=='__main__':
 import sys
 sys.stdout.reconfigure(encoding='utf-8',errors='replace')
 if sys.argv[1]=='initial':
  jobs=[('D29','中航京能REIT_2026年更新招募说明书_508096_20260706.pdf','https://big5.sse.com.cn/site/cht/www.sse.com.cn/disclosure/fund/announcement/c/new/2026-07-06/508096_20260706_GW8D.pdf'),('D22','南方区域电力市场运行规则_试行_2025年V1.0版.pdf','https://nfj.nea.gov.cn/hdhy/zlxz/202506/P020250625360641274024.pdf')]
  def run(j):
   try:return save(*j,expect='pdf')
   except Exception as e:return {'id':j[0],'error':str(e)}
  with concurrent.futures.ThreadPoolExecutor(max_workers=3) as ex:
   for x in ex.map(run,jobs):print(json.dumps(x,ensure_ascii=False),flush=True)
 if sys.argv[1]=='batch2':
  jobs=[('D16','2025云南统计年鉴.zip','https://www.yn.gov.cn/sjfb/tjnj_2/202606/P020260626373849283283.zip'),('D15','中华人民共和国2025年国民经济和社会发展统计公报.html','https://www.stats.gov.cn/sj/zxfbhjd/202602/t20260228_1962662.html'),('D19','云铝股份000807_2025年年度报告全文.pdf','https://static.cninfo.com.cn/finalpage/2026-03-28/1225043142.PDF')]
  for j in jobs:
   try:print(json.dumps(save(*j),ensure_ascii=False),flush=True)
   except Exception as e:print(str(e),flush=True)
 if sys.argv[1]=='water':
  ls,r=links('https://wcb.yn.gov.cn/szygb_0/')
  (BASE/'_provenance'/'water_catalog.html').write_bytes(r.content)
  jobs=[];seen=set()
  for t,u in ls:
   if '/szygb_0/' not in u or u in seen:continue
   y=re.search(r'(19\d{2}|20\d{2})年',t)
   if y and u.endswith('.html'):
    jobs.append(('D14',y[1]+'年云南省水资源公报.html',u,None));seen.add(u)
   elif u.lower().endswith('.pdf'):
    yr=int(re.search(r'/szygb_0/(\d{4})',u)[1])-1
    jobs.append(('D14',str(yr)+'年云南省水资源公报_'+u.split('/')[-1],u,'pdf'));seen.add(u)
  def worker(j):
   try:return save(j[0],j[1],j[2],j[3])
   except Exception as e:return {'id':j[0],'url':j[2],'error':str(e)}
  with concurrent.futures.ThreadPoolExecutor(max_workers=5) as ex:
   out=list(ex.map(worker,jobs))
  (BASE/'_provenance'/'water_downloads.json').write_text(json.dumps(out,ensure_ascii=False,indent=2),encoding='utf-8')
  print(json.dumps(out,ensure_ascii=False),flush=True)
 if sys.argv[1]=='inspect':
  with concurrent.futures.ThreadPoolExecutor(max_workers=6) as ex:
   for u,res in zip(sys.argv[2:],ex.map(inspect,sys.argv[2:])):print(json.dumps(res,ensure_ascii=False))
