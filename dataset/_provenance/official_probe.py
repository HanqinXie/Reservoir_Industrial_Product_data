from download_official import *
import sys
sys.stdout.reconfigure(encoding='utf-8')
us=['https://international-aluminium.org/statistics/primary-aluminium-smelting-energy-intensity/','https://archive.international-aluminium.org/statistics/primary-aluminium-production/','https://www.shfe.com.cn/data/dailydata/kx/kx20261026.dat','https://www.shfe.com.cn/data/dailydata/20261026dailystock.dat','https://www.shfe.com.cn/data/dailydata/20261023weeklystock.dat']
def f(u):
 try:
  r=requests.get(u,timeout=25,proxies={'https':'http://127.0.0.1:7890','http':'http://127.0.0.1:7890'} if 'aluminium' in u else {})
  if r.status_code==200:
   name='iai_energy_page.html' if 'energy-intensity' in u else 'iai_production_page.html' if 'aluminium' in u else u.split('/')[-1]
   (BASE/'_provenance'/name).write_bytes(r.content)
  return {'url':u,'status':r.status_code,'bytes':len(r.content),'head':r.text[:100]}
 except Exception as e:return {'url':u,'error':str(e)}
for x in concurrent.futures.ThreadPoolExecutor(5).map(f,us): print(json.dumps(x,ensure_ascii=False),flush=True)
