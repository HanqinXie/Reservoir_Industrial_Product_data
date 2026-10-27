from official_collect import *
us=['https://data.stats.gov.cn/dg/website/static/js/project/'+x+'.js' for x in ['project_national_datatree','project_national_home']]
def f(u):
 try:
  r=get(u,30);p=BASE/'_provenance'/u.split('/')[-1];p.write_bytes(r.content);return (p.name,len(r.content))
 except Exception as e:return str(e)
print(list(concurrent.futures.ThreadPoolExecutor(4).map(f,us)))
