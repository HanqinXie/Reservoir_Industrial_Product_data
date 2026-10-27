from official_collect import *
def call(path,params=None,payload=None,name=None):
 u='https://data.stats.gov.cn/dg/website'+path
 r=requests.get(u,params=params,timeout=40,headers={'Referer':'https://data.stats.gov.cn/dg/website/page.html','User-Agent':'Mozilla/5.0'}) if payload is None else requests.post(u,json=payload,timeout=70,headers={'Referer':'https://data.stats.gov.cn/dg/website/page.html','User-Agent':'Mozilla/5.0'})
 print(r.status_code,len(r.content),u,flush=True)
 try:j=r.json()
 except Exception:print(r.text[:100],flush=True);return None
 if name:
  p=folder('D15')/(name+'.json');p.write_bytes(r.content);record({'id':'D15','file':p.relative_to(BASE).as_posix(),'url':r.url,'method':'POST' if payload else 'GET','parameters':payload or params,'bytes':len(r.content)})
 return j
if __name__=='__main__':
 j=call('/publicrelease/web/external/new/queryIndexTreeAsync',{'code':'6'},name='国家数据_分省年度_指标根目录')
 print(json.dumps(j,ensure_ascii=False)[:15000],flush=True)
