import requests,sys,concurrent.futures
from pathlib import Path
from bs4 import BeautifulSoup
sys.stdout.reconfigure(encoding='utf-8');p=Path('standards/_provenance')
def f(it):
 id,key=it
 try:
  r=requests.get('https://www.kqqw.com/e/sch/index.php',params={'keyboard':key,'Submit':'搜索'},timeout=15);(p/(id+'_kqqw_search.html')).write_bytes(r.content);s=BeautifulSoup(r.content,'html.parser');return id,r.status_code,s.get_text(' ',strip=True)[-1000:],[(a.text,a.get('href')) for a in s.find_all('a',href=True) if key.split('-')[0] in a.text]
 except Exception as e:return id,str(e)
with concurrent.futures.ThreadPoolExecutor(max_workers=5) as e:
 for a in e.map(f,[('S01','17621'),('S03','50587'),('S07','29741'),('S08','1196-2023'),('S09','2589-2020')]):print(a)
