from official_collect import *
s=(BASE/'_provenance'/'iai_current_production.html').read_text(encoding='utf-8')
token=re.search(r'window.ALVIS_API_TOKEN = "([^"]+)"',s)[1]
api='https://alvis.international-aluminium.org/api'
for i,slug in [('D17','primary-aluminium-smelting-energy-intensity'),('D18','primary-aluminium-production')]:
 u=api+'/publication/?publication='+slug
 try:
  r=requests.get(u,headers={'X-AUTH-TOKEN':token,'Referer':'https://international-aluminium.org/'},timeout=60)
  print(i,r.status_code,len(r.content),flush=True)
  if r.status_code==200:
   j=r.json();p=folder(i)/(slug+'_当前官网API完整响应.json');p.write_bytes(r.content)
   record({'id':i,'file':str(p.relative_to(BASE)),'url':u,'bytes':len(r.content),'method':'GET','description':'Public frontend API, authentication header deliberately omitted from provenance.'})
   print(json.dumps({'topkeys':list(j),'sample':str(j)[:1600]},ensure_ascii=False),flush=True)
   pub=j['data']['publication']; print(i,'publication keys',list(pub),'chartkeys',list(pub.get('charts',{})),flush=True)
   for fmt in ['csv','xlsx']:
    u=api+'/publication/'+slug+'/export/'
    query={'filter':json.dumps({'format':fmt,'allData':True},separators=(',',':'))}
    rr=requests.get(u,params=query,headers={'X-AUTH-TOKEN':token,'Referer':'https://international-aluminium.org/'},timeout=90)
    if rr.status_code!=200:print(i,fmt,rr.status_code,flush=True);continue
    jj=rr.json()
    if jj.get('data',{}).get('fileContent'):
     import base64
     b=base64.b64decode(jj['data']['fileContent']);p=folder(i)/(slug+'_全部历史数据_当前官网导出.'+fmt);p.write_bytes(b)
     record({'id':i,'file':str(p.relative_to(BASE)),'url':rr.url,'bytes':len(b),'method':'GET','description':'Official ALVIS Export All Data; public frontend auth header omitted.'})
     print(i,fmt,'saved',len(b),flush=True)
    else:print(i,fmt,'response keys',list(jj),str(jj)[:300],flush=True)
 except Exception as e:print(str(e),flush=True)
