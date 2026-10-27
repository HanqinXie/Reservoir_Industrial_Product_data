import requests,json,concurrent.futures,sys
from pathlib import Path
sys.stdout.reconfigure(encoding='utf-8');p=Path('standards/_provenance')
def f(it):
 id,key=it;r=requests.post('https://hbba.sacinfo.org.cn/stdQueryList',data=dict(current=1,size=20,key=key),timeout=30);(p/('hb_title_'+id+'.json')).write_bytes(r.content);print(id,r.status_code,r.text[:5000])
with concurrent.futures.ThreadPoolExecutor(max_workers=2) as e:list(e.map(f,[('S02','水库调度规程编制导则'),('S18','水工建筑物与堰槽测流规范')]))
s=requests.Session();u='https://openstd.samr.gov.cn/bzgk/std/newGbInfo?hcno=2D9CE8D164C7157B20823329A97D0750';s.get(u);r=s.get('https://openstd.samr.gov.cn/bzgk/std/showGb?type=download&hcno=2D9CE8D164C7157B20823329A97D0750&request_locale=zh_CN',headers={'Referer':u,'User-Agent':'Mozilla/5.0'},timeout=30);(p/'S10_download_with_ref.html').write_bytes(r.content);print('opendownload',r.status_code,r.url,len(r.content))
u='https://picpolicy.mofcom.gov.cn/file/20261020/20261020163423512.doc';r=requests.get(u,timeout=30);(p/'S17_draft.doc').write_bytes(r.content);print('draft',r.status_code,len(r.content),r.content[:12])
