from nbs_api import *
import pandas as pd
for label,cid in [('发电量','f76c5af9a1604d1b906463b208bdd675'),('水力发电量','5a58168195604a348e6a5d909552187e'),('氧化铝产量','cc561db90e694bdd889347b75f538e3a'),('铝材产量','5218fbb0c5994a7f8d8a6fecb9ebea1b')]:
 j=call('/publicrelease/web/external/new/queryIndicatorsByCid',{'cid':cid},name='国家数据_分省月度_'+label+'_指标')
 if not j or not j.get('data',{}).get('list'):continue
 inds=j['data']['list'];ids=[x['_id'] for x in inds]
 print(label,[(x['i_showname'],x['daterange_sdate']) for x in inds],flush=True)
 params={'cid':cid,'rootId':'f4c6cd795fea436c807163397dd36b98','indicatorIds':ids,'daCatalogId':'','das':[{'text':'云南省','value':'530000000000'}],'showType':1,'dts':['199801MM-202609MM']}
 j=call('/publicrelease/web/external/stream/esData',payload=params,name='云南省_1998-202609月度_'+label+'_官方原始数据')
 if j and j.get('data'):
  out=[]
  for x in j['data']:
   for v in x.get('values',[]):out.append({'period':x.get('name'),'period_code':x.get('code'),**v})
  pd.DataFrame(out).to_csv(folder('D15')/('云南省_1998-202609月度_'+label+'_原表展开.csv'),index=False,encoding='utf-8-sig')
  nonempty=[x for x in out if x.get('value') not in ['',None]];print(label,'rows',len(out),'nonempty',len(nonempty),'dates',nonempty[0]['period'] if nonempty else '',nonempty[-1]['period'] if nonempty else '',flush=True)
