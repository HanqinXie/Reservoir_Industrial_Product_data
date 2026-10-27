from official_collect import *
us=[('GET','https://data.stats.gov.cn/easyquery.htm',{'m':'getTree','dbcode':'fsnd','id':'zb','wdcode':'zb'}),('GET','https://data.stats.gov.cn/easyquery.htm',{'m':'QueryData','dbcode':'fsnd','rowcode':'zb','colcode':'sj','wds':'[{"wdcode":"reg","valuecode":"530000"}]','dfwds':'[{"wdcode":"sj","valuecode":"LAST10"}]'}),('GET','https://data.stats.gov.cn/easyquery.htm',{'cn':'E0103'}),('GET','https://data.stats.gov.cn/',{})]
for method,u,params in us:
 try:
  r=requests.get(u,params=params,timeout=25,headers={'User-Agent':'Mozilla/5.0','Referer':'https://data.stats.gov.cn/','X-Requested-With':'XMLHttpRequest'})
  record({'id':'D15','url':r.url,'http_status':r.status_code,'bytes':len(r.content),'response_start':r.text[:100]})
  print(r.url,r.status_code,len(r.content),r.text[:200],flush=True)
  if r.status_code==200 and r.text.lstrip().startswith(('[','{')):
   j=r.json();p=folder('D15')/('国家数据_'+str(len(params))+'_API响应.json');p.write_bytes(r.content);print(json.dumps(j,ensure_ascii=False)[:9000],flush=True)
 except Exception as e:record({'id':'D15','url':u,'error':str(e)});print(str(e),flush=True)
