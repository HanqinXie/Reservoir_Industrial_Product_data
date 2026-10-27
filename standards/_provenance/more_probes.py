from pathlib import Path
import requests,sys,concurrent.futures,json
from bs4 import BeautifulSoup
sys.stdout.reconfigure(encoding='utf-8');p=Path('standards/_provenance')
urls={'S18_hn':'https://www.hnzhsl.com/standard/14','S02_yz':'https://www.yzbzpt.cn/BzInfoDetail/6b7d065a-85d1-48ad-9e83-b0209eba76e4','S07_http':'http://www.jxzaaq.com/laws_regulations_details/995.html','S07_nonwww':'https://jxzaaq.com/laws_regulations_details/995.html','S17_doc':'https://picpolicy.mofcom.gov.cn/file/20261020/20261020163423512.doc','S10_mirror':'https://23922130.s21i.faiusr.com/61/3/ABUIABA9GAAgkdD5wQYogLDzHA.pdf','S09_mirror':'https://img.antpedia.com/standard/files/pdfs_ora/GB2020/GB_T%202589-2020.pdf','S04_full':'https://hbba.sacinfo.org.cn/portal/download/dad3b1e8b98ce2592cce217014d06fac01164059be7fe4f05be4ee0c44b8fdb2'}
def f(it):
 id,u=it
 try:
  r=requests.get(u,timeout=25);ext='.pdf' if r.content.startswith(b'%PDF') else ('.doc' if r.content.startswith(b'\xd0\xcf') else '.html');(p/(id+ext)).write_bytes(r.content);s=BeautifulSoup(r.content,'html.parser') if ext=='.html' else None;links=[(a.get_text(' ',strip=True),requests.compat.urljoin(u,a.get('href',''))) for a in s.find_all('a',href=True) if any(w in a.get('href','').lower() for w in ['.pdf','.doc','online','read','download','mwr'])] if s else [];return id,r.status_code,len(r.content),r.url,links
 except Exception as e:return id,str(e)
with concurrent.futures.ThreadPoolExecutor(max_workers=8) as e:
 for r in e.map(f,urls.items()):print(r)
