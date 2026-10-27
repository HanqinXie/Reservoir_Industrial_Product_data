from nbs_api import *
import pandas as pd
root='c4d82af16c3d4f0cb4f09d4af7d5888e'
catalog='ade19f093ebe43a5a773087039c5fedc'
ids=['df1221c66aef40c5bc82bb1024eff1d1','eafb7863b41d471e9d5c8a58d4aa3531','da02dfca04f94670b6506d071c52e053']
params={'cid':catalog,'rootId':root,'indicatorIds':ids,'daCatalogId':'','das':[{'text':'云南省','value':'530000000000'}],'showType':1,'dts':['1991YY-2025YY']}
j=call('/publicrelease/web/external/stream/esData',payload=params,name='云南省_1991-2025发电量水电火电_官方原始数据')
print(json.dumps(j,ensure_ascii=False)[:5000],flush=True)
if j and j.get('data'):
 out=[]
 for x in j['data']:
  for v in x.get('values',[]):out.append({'period':x.get('name'),'period_code':x.get('code'),**v})
 pd.DataFrame(out).to_csv(folder('D15')/'云南省_1991-2025发电量水电火电_原表展开.csv',index=False,encoding='utf-8-sig')
# Search the official indicator tree by the product name, with the public query interface.
j=call('/publicrelease/web/external/new/queryIndicatorsByCid',{'cid':root,'name':'铝'},name='国家数据_分省年度_铝指标检索')
print(json.dumps(j,ensure_ascii=False)[:8000],flush=True)
