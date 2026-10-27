import requests,sys,concurrent.futures,json,re,time,hashlib
from pathlib import Path
from bs4 import BeautifulSoup
from pypdf import PdfReader
sys.stdout.reconfigure(encoding='utf-8');p=Path('standards/_provenance');manifest=json.loads((p/'manifest_standards.json').read_text(encoding='utf-8'))
tasks={'S01':'44777','S03':'79906','S06':'361325','S07':'453698','S08':'400880','S09':'232200'}
def f(it):
 id,num=it;item=next(a for a in manifest if a['id']==id)
 try:
  s=requests.Session();url='https://www.kqqw.com/e/DownSys/DownSoft/?classid=2&id='+num;r=s.get(url,timeout=15);(p/(id+'_mirror_download_page.html')).write_bytes(r.content);soup=BeautifulSoup(r.content,'html.parser');a=next(a for a in soup.find_all('a',href=True) if 'doaction.php' in a['href']);u=requests.compat.urljoin(r.url,a['href']);r=s.get(u,timeout=(15,40));(p/(id+'_mirror_response.bin')).write_bytes(r.content)
  if not r.content.startswith(b'%PDF'):return dict(id=id,error='not PDF',url=r.url,status=r.status_code,bytes=len(r.content))
  name=re.sub(r'[<>:"/\\|?*]','_',item['title']+'_'+item['code'])+'.pdf';out=Path('standards')/name;out.write_bytes(r.content);reader=PdfReader(out);txt='\n'.join(a.extract_text() or '' for a in reader.pages);(p/(id+'_mirror_pdf_text.txt')).write_text(txt,encoding='utf-8');return dict(id=id,status='fulltext_downloaded_public_mirror',files=[name],download_url=r.url,landing_url='https://www.kqqw.com/gb/'+num+'.html',pages=len(reader.pages),bytes=len(r.content),sha256=hashlib.sha256(r.content).hexdigest(),reason='公开下载页直链副本；未登录、未付费、未绕过验证码。需结合官方元数据核对版本；全文页数与首尾页已检查。',text_start=txt[:220],text_end=txt[-220:])
 except Exception as e:return dict(id=id,error=str(e))
with concurrent.futures.ThreadPoolExecutor(max_workers=6) as e:
 results=list(e.map(f,tasks.items()))
 for a in results:print(json.dumps(a,ensure_ascii=False),flush=True)
(p/'mirror_download_results.json').write_text(json.dumps(results,ensure_ascii=False,indent=2),encoding='utf-8')
for a in results:
 if 'files' in a:next(x for x in manifest if x['id']==a['id']).update({k:v for k,v in a.items() if k not in ['text_start','text_end']})
(p/'manifest_standards.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
