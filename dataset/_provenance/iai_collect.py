from official_collect import *
for i,slug in [('D17','primary-aluminium-smelting-energy-intensity'),('D18','primary-aluminium-production')]:
 u=f'https://archive.international-aluminium.org/statistics/{slug}/?publication={slug}'
 x=fetch((i,slug+'_官方数据页面.html',u))
 if 'file' not in x:continue
 s=BeautifulSoup((BASE/x['file']).read_bytes(),'html.parser')
 print(i,json.dumps({'scripts':[x.get('src') for x in s.select('script[src]') if any(a in x.get('src','') for a in ['stat','graph','chart'])],'exports':[str(a) for a in s.select('a,button') if 'csv' in str(a).lower()],'inline':[(str(a)[:300]) for a in s.select('script:not([src])') if any(v in str(a).lower() for v in ['statistic','var data','series','ajax'])]},ensure_ascii=False),flush=True)
