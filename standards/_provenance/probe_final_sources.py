from pathlib import Path
import requests,sys,concurrent.futures
from bs4 import BeautifulSoup
sys.stdout.reconfigure(encoding='utf-8');p=Path('standards/_provenance')
urls={'S06_kqqw':'https://kkk.kqqw.com/bzgf2/BZ-F1F08FCFAC5D62FF20230407ib.pdf','S09_gov':'http://ft.panzhihua.gov.cn/uploadfiles/202108/12/2021081217202347802674.pdf','S09_gov_https':'https://ft.panzhihua.gov.cn/uploadfiles/202108/12/2021081217202347802674.pdf','S10_isc':'https://oa.china-isc.org.cn/bizattach/Base_Announce/521000007liudajun/GB%2017167-2025%20%E7%94%A8%E8%83%BD%E5%8D%95%E4%BD%8D%E8%83%BD%E6%BA%90%E8%AE%A1%E9%87%8F%E5%99%A8%E5%85%B7%E9%85%8D%E5%A4%87%E5%92%8C%E7%AE%A1%E7%90%86%E9%80%9A%E5%88%99.pdf','S01_cspress':'https://test2026.cspress.com.cn/index.php?c=show&id=5155','S07_jx_m':'https://www.jxzaaq.com/laws_regulations_details/995.html?m=1'}
def f(it):
 id,u=it
 try:
  r=requests.get(u,timeout=20);ext='.pdf' if r.content.startswith(b'%PDF') else '.html';(p/(id+ext)).write_bytes(r.content);s=BeautifulSoup(r.content,'html.parser') if ext=='.html' else None;links=[(a.get_text(' ',strip=True),requests.compat.urljoin(u,a.get('href',''))) for a in s.find_all('a',href=True) if any(w in a.get('href','').lower() for w in ['.pdf','.doc','download','downsoft'])] if s else [];return id,r.status_code,len(r.content),links
 except Exception as e:return id,str(e)
with concurrent.futures.ThreadPoolExecutor(max_workers=6) as e:
 for r in e.map(f,urls.items()):print(r)
