from pathlib import Path
import re,requests,sys,hashlib,concurrent.futures,json,time
from PIL import Image
sys.stdout.reconfigure(encoding='utf-8');p=Path('standards/_provenance');base='http://121.36.94.83:9008/jsp/yishenqing/appladd/biaozhunfile/flash/'
tasks=[];meta={}
for id in ['S02','S18']:
 t=(p/(id+'_mwr_preview.html')).read_text(encoding='utf-8');n=int(re.search(r'pageTotal="(\d+)"',t).group(1));fid=re.search(r'fnameId="(.*?)"',t).group(1);meta[id]=dict(pages=n,file_id=fid);folder=p/(id+'_official_pages');folder.mkdir(exist_ok=True)
 for k in range(1,n+1):tasks.append((id,k,n,fid))
def f(t):
 id,k,n,fid=t;target=p/(id+'_official_pages')/(str(k).zfill(3)+'.png')
 for attempt in range(3):
  try:
   if not target.exists():
    r=requests.get(base+'imgServlet_Stream.jsp',params=dict(fnameId=fid,pnum=n,code=k),timeout=(10,20));r.raise_for_status();target.write_bytes(r.content)
   with Image.open(target) as im:im.verify()
   return dict(id=id,page=k,bytes=target.stat().st_size,sha256=hashlib.sha256(target.read_bytes()).hexdigest(),status='ok')
  except Exception as ex:
   if target.exists():target.unlink()
   if attempt==2:return dict(id=id,page=k,status='error',reason=str(ex))
with concurrent.futures.ThreadPoolExecutor(max_workers=4) as ex:
 results=[]
 for i,r in enumerate(ex.map(f,tasks),1):
  results.append(r)
  if i%25==0 or i==len(tasks):print('downloaded',i,'/',len(tasks),'errors',sum(x['status']=='error' for x in results),flush=True)
(p/'mwr_pages_manifest.json').write_text(json.dumps(dict(meta=meta,pages=results),ensure_ascii=False,indent=2),encoding='utf-8')
