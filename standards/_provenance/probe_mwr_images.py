from pathlib import Path
import re,requests,sys,hashlib,concurrent.futures,json,time
from PIL import Image
sys.stdout.reconfigure(encoding='utf-8');p=Path('standards/_provenance');base='http://121.36.94.83:9008/jsp/yishenqing/appladd/biaozhunfile/flash/'
def probe(id):
 text=(p/(id+'_mwr_preview.html')).read_text(encoding='utf-8');n=int(re.search(r'pageTotal="(\d+)"',text).group(1));fid=re.search(r'fnameId="(.*?)"',text).group(1);folder=p/(id+'_official_pages');folder.mkdir(exist_ok=True)
 for k in [1,2,n]:
  u=base+'imgServlet_Stream.jsp';r=requests.get(u,params=dict(fnameId=fid,pnum=n,code=k),timeout=20);f=folder/(str(k).zfill(3)+'.png');f.write_bytes(r.content)
  try:im=Image.open(f);print(id,k,r.status_code,len(r.content),im.format,im.size)
  except Exception as e:print(id,k,'ERROR',r.status_code,len(r.content),r.content[:100])
with concurrent.futures.ThreadPoolExecutor(max_workers=2) as e:list(e.map(probe,['S02','S18']))
