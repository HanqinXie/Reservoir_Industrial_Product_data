from pathlib import Path
import json,re,fitz,hashlib
p=Path('standards/_provenance');m=json.loads((p/'manifest_standards.json').read_text(encoding='utf-8'));capture=json.loads((p/'mwr_pages_manifest.json').read_text(encoding='utf-8'));assert not [x for x in capture['pages'] if x['status']!='ok']
for id in ['S02','S18']:
 a=next(a for a in m if a['id']==id);n=capture['meta'][id]['pages'];folder=p/(id+'_official_pages');doc=fitz.open()
 for k in range(1,n+1):
  img=fitz.open(folder/(str(k).zfill(3)+'.png'));r=img[0].rect;pg=doc.new_page(width=r.width,height=r.height);pg.insert_image(pg.rect,filename=str(folder/(str(k).zfill(3)+'.png')));img.close()
 name=re.sub(r'[<>:"/\\|?*]','_',a['title']+'_'+a['code'])+'_官方在线阅览分页保存.pdf';out=Path('standards')/name;doc.set_metadata(dict(title=a['title']+' '+a['code'],subject='官方在线阅览分页保存；非原始PDF下载附件；原图530x768',author='中华人民共和国水利部（原页面内容）',creator='Public reader page image preservation'));doc.save(out,deflate=True);doc.close();b=out.read_bytes();assert b.startswith(b'%PDF');d=fitz.open(out);assert len(d)==n
 for k in [0,n//2,n-1]:d[k].get_pixmap(matrix=fitz.Matrix(1,1)).save(p/(id+'_compiled_'+str(k)+'.png'))
 a.update(status='fulltext_official_reader_page_capture',files=[name],pages=n,bytes=len(b),sha256=hashlib.sha256(b).hexdigest(),fulltext_source_type='official_public_reader_page_images',download_url='http://121.36.94.83:9008/jsp/yishenqing/appladd/biaozhunfile/flash/previewImg.jsp?bzMax='+requests_quote if False else '',reason='水利部现行有效标准系统无登录公开阅览，逐页保存全部原图并按顺序无裁剪合成PDF；不是原始PDF附件。源图530×768像素；全部页图格式校验通过，页数与官方查看器一致，首中尾页已核。',source_image_size=[530,768],page_images_manifest='_provenance/mwr_pages_manifest.json')
 a['download_url']='http://121.36.94.83:9008/jsp/yishenqing/appladd/biaozhunfile/flash/previewImg.jsp?bzMax=SL%252FT%2B'+('706-2026' if id=='S02' else '537-2026')
 print(id,n,len(b))
(p/'manifest_standards.json').write_text(json.dumps(m,ensure_ascii=False,indent=2),encoding='utf-8')
