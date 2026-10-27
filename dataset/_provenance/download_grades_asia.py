from pathlib import Path
import json,threading,h5py
import download_scientific as segmented
from acquire_root_sources import BASE,RECORDS,directory,digest,write_json

identifier='D03';p=directory(identifier)
name='GRADES_Q_v01_pfaf_04_19790101_20131231.nc'
partial=p/(name+'.part');out=p/name
task={'id':identifier,'name':name,'source_url':'https://drive.usercontent.google.com/download?id=1GER-t-DBdb9FWBkpW1J9HFlDN3TXbtxE&export=download&confirm=t','expected_bytes':23780171996,'range_workers':48}
r=RECORDS[identifier].copy();r['files']=[]
threading.Thread(target=segmented.progress_log,daemon=True).start()
try:
    probe={}
    if not out.exists():
        if not segmented.segmented_download(task,partial,probe):raise ValueError('HTTP ranges unavailable')
        partial.replace(out)
    assert out.stat().st_size==task['expected_bytes']
    r['files'].append({'path':str(out.relative_to(BASE)),'url':task['source_url'],'bytes':out.stat().st_size,'sha256':digest(out)})
    with h5py.File(out,'r')as h:
        r['variables']={k:{'shape':list(v.shape),'dtype':str(v.dtype),'units':str(v.attrs.get('units',''))}for k,v in h.items() if isinstance(v,h5py.Dataset)}
        r['time_range_days_since_1979_01_01']=[float(h['time'][0]),float(h['time'][-1])]
        assert h['Q'].shape==(12784,464952)
    r.update(status='downloaded_regional_subset',reason='按用户云南及相关上游流域范围下载原始GRADES v01亚洲pfaf04原始文件。NetCDF无需解压；未下载其他洲与全球格点径流。此为1979–2013旧版，官方推荐后继GRADES-hydroDL，未混用版本。',scope='pfaf04亚洲；1979-01-01至2013-12-31',http_range_validation=probe)
except Exception as e:
    r.update(status='download_failed',reason=repr(e))
finally:
    segmented.STOP_LOG.set()
    write_json(p/'_provenance'/'manifest.json',r)
    manifest=BASE/'_provenance'/'manifest_root.json'
    j=json.loads(manifest.read_text(encoding='utf-8'));j=[a for a in j if a['id']!=identifier]+[r];write_json(manifest,sorted(j,key=lambda a:a['id']))
    print('FINAL',r['status'],r.get('reason'),flush=True)
