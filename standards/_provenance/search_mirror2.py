import requests,sys,concurrent.futures
from pathlib import Path
from bs4 import BeautifulSoup
sys.stdout.reconfigure(encoding='utf-8');p=Path('standards/_provenance')
def f(it):
 id,key=it
 try:
  r=requests.get('https://www.kqqw.com/e/sch/index.php',params={'keyboard':key,'Submit':'搜索'},timeout=15);(p/(id+'_kqqw_search2.html')).write_bytes(r.content);s=BeautifulSoup(r.content,'html.parser');return id,[(a.text,a.get('href')) for a in s.find_all('a',href=True) if key in a.text]
 except Exception as e:return id,str(e)
with concurrent.futures.ThreadPoolExecutor(max_workers=4) as e:
 for a in e.map(f,[('S08','1196'),('S09','2589'),('S02','水库调度规程编制导则'),('S18','水工建筑物与堰槽测流规范')]):print(a)
