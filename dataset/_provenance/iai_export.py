from official_collect import *
for i,slug in [('D17','primary-aluminium-smelting-energy-intensity'),('D18','primary-aluminium-production')]:
 p=next(folder(i).glob('*.html'));s=BeautifulSoup(p.read_bytes(),'html.parser')
 inline=next(a.get_text() for a in s.select('script:not([src])') if 'pubId' in str(a))
 pubid=re.search(r'var pubId = (\d+)',inline)[1];nonce=re.search(r"var sgNonce = '([^']+)'",inline)[1]
 cols=','.join(a['data-id'] for a in s.select('.statistics-graphing-columns .footer-button[data-id]'))
 cats=','.join(a['data-id'] for a in s.select('.statistics-graphing-categories .footer-button[data-id]') if a['data-id']!='sum')
 rows=','.join(a['data-id'] for a in s.select('.statistics-graphing-rows .footer-button[data-id]'))
 ys=[int(x['value']) for x in s.select('.date-range-year select option')];my=re.search(r'var maxDate = (.*?);',inline)
 print(i,cols,cats,rows,min(ys),max(ys),my[1] if my else '',flush=True)
 params={'_wpnonce':nonce,'pi':pubid,'df':f'{min(ys)},01,01','dt':f'{max(ys)},12,01','gfm':'12' if i=='D17' else '1','cols':cols,'cats':cats,'rows':rows,'action':'fsd_download','all':'true','title':s.select_one('h1').get_text(),'col-title':'REGION','cat-title':'Type' if i=='D17' else '', 'row-title':''}
 api='https://archive.international-aluminium.org/wp-admin/admin-ajax.php'
 try:
  r=requests.post(api,files={k:(None,v) for k,v in params.items()},timeout=70,headers={'Referer':f'https://archive.international-aluminium.org/statistics/{slug}/','User-Agent':'Mozilla/5.0'})
  out={'id':i,'url':api,'method':'POST','parameters':{k:v for k,v in params.items() if k!='_wpnonce'},'http_status':r.status_code,'response':r.text[:2000]};record(out)
  print(i,r.status_code,r.text[:1000],flush=True)
  if r.status_code==200 and r.text.startswith('success,'):
   u=r.text.split(',',1)[1].strip();print(json.dumps(fetch((i,slug+'_全部历史数据_官方导出.csv',u)),ensure_ascii=False),flush=True)
  if r.status_code!=200:
   params.update(action='fsd_data_graphing',df=f'{min(ys)}-01-01',dt=f'{max(ys)}-'+('12' if i=='D17' else '09')+'-01',catTitle='Type' if i=='D17' else '')
   r=requests.post(api,files={k:(None,v) for k,v in params.items()},timeout=70,headers={'Referer':f'https://archive.international-aluminium.org/statistics/{slug}/','User-Agent':'Mozilla/5.0'})
   record({'id':i,'url':api,'method':'POST','http_status':r.status_code,'action':'fsd_data_graphing','response_start':r.text[:300]})
   print(i,'data',r.status_code,r.text[:1000],flush=True)
   if r.status_code==200 and r.text.startswith('success,'):
    html=r.text.split(',',6)[-1];p=folder(i)/(slug+'_全部历史数据表.html');p.write_text(html,encoding='utf-8')
    record({'id':i,'file':str(p.relative_to(BASE)),'url':api,'action':'fsd_data_graphing','parameters':{k:v for k,v in params.items() if k!='_wpnonce'},'bytes':p.stat().st_size})
 except Exception as e:record({'id':i,'url':api,'error':str(e)});print(str(e),flush=True)
