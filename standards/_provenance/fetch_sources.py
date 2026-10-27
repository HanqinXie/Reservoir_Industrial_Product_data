from pathlib import Path
import re,json,requests,concurrent.futures
from bs4 import BeautifulSoup
root=Path.cwd(); out=root/'standards'/'_provenance'; out.mkdir(parents=True,exist_ok=True)
s=(root/'水库_工业库存_研究计划与文献数据标准包_20261026'/'04_standards_and_rules.md').read_text(encoding='utf-8')
items=[]
for match in re.finditer(r'### (S\d+) · (.*?)\n(.*?)(?=\n### |\n## 5\.)',s,re.S):
 id,title,body=match.groups();code=re.search(r'\*\*编号：\*\*(.*?)｜',body).group(1);url=re.search(r'入口\]\((.*?)\)',body).group(1);items.append(dict(id=id,title=title,code=code,source_url=url,status='pending',files=[],reason=''))
(out/'manifest_standards.json').write_text(json.dumps(items,ensure_ascii=False,indent=2),encoding='utf-8')
def fetch(item):
 try:
  r=requests.get(item['source_url'],timeout=35);r.encoding=r.apparent_encoding
  ext='.pdf' if r.content.startswith(b'%PDF') else '.html'
  (out/(item['id']+'_source'+ext)).write_bytes(r.content)
  soup=BeautifulSoup(r.content,'html.parser')
  links=[{'text':a.get_text(' ',strip=True),'url':requests.compat.urljoin(r.url,a.get('href',''))} for a in soup.find_all('a',href=True) if any(w in a.get('href','').lower() for w in ['.pdf','.doc','.zip','download'])]
  return dict(id=item['id'],status=r.status_code,url=r.url,bytes=len(r.content),content_type=r.headers.get('content-type'),links=links,text=soup.get_text(' ',strip=True)[-15000:])
 except Exception as e:return dict(id=item['id'],error=str(e))
with concurrent.futures.ThreadPoolExecutor(max_workers=10) as p: res=list(p.map(fetch,items))
(out/'initial_fetch.json').write_text(json.dumps(res,ensure_ascii=False,indent=2),encoding='utf-8')
for a in res:print(json.dumps({k:v for k,v in a.items() if k!='text'},ensure_ascii=False))
