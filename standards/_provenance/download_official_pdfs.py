from pathlib import Path
import json,requests,re,hashlib,concurrent.futures,sys
from pypdf import PdfReader
sys.stdout.reconfigure(encoding='utf-8')
p=Path('standards/_provenance');items=json.loads((p/'manifest_standards.json').read_text(encoding='utf-8'));fetch=json.loads((p/'initial_fetch.json').read_text(encoding='utf-8'))
def dl(item):
 if not 11<=int(item['id'][1:])<=16:return
 links=next(a['links'] for a in fetch if a['id']==item['id']);url=next(a['url'] for a in links if '.pdf' in a['url']);r=requests.get(url,timeout=45);assert r.content.startswith(b'%PDF'),(r.status_code,r.headers)
 name=re.sub(r'[<>:"/\\|?*]','_',item['title']+'_'+item['code'])+'.pdf';out=Path('standards')/name;out.write_bytes(r.content);reader=PdfReader(out);txt='\n'.join(a.extract_text() or '' for a in reader.pages);(p/(item['id']+'_pdf_text.txt')).write_text(txt,encoding='utf-8');item.update(status='fulltext_downloaded',files=[name],download_url=url,reason='政府网站公开PDF原始附件；PDF魔数与全部页面可解析。',pages=len(reader.pages),bytes=len(r.content),sha256=hashlib.sha256(r.content).hexdigest());print(item['id'],len(reader.pages),len(txt),txt[:90]);return item
with concurrent.futures.ThreadPoolExecutor(max_workers=6) as x: results=list(x.map(dl,items))
(p/'manifest_standards.json').write_text(json.dumps(items,ensure_ascii=False,indent=2),encoding='utf-8')
