import io,json,requests,h5py
from pathlib import Path

class HTTPFile(io.RawIOBase):
    def __init__(self):
        self.size=23780171996;self.pos=0;self.cache={};self.block=1024*1024;self.calls=0
        self.local=next(Path('dataset').glob('D03_*/*.part'))
        self.url='https://drive.usercontent.google.com/download'
        self.params={'id':'1GER-t-DBdb9FWBkpW1J9HFlDN3TXbtxE','export':'download','confirm':'t'}
    def readable(self):return True
    def seekable(self):return True
    def tell(self):return self.pos
    def seek(self,offset,whence=0):
        self.pos=offset if whence==0 else self.pos+offset if whence==1 else self.size+offset
        return self.pos
    def read(self,n=-1):
        n=min(n if n>=0 else self.size-self.pos,self.size-self.pos);start=self.pos;end=start+n
        if end<=self.local.stat().st_size:
            with self.local.open('rb')as f:f.seek(start);data=f.read(n)
        else:
            parts=[]
            for index in range(start//self.block,(end-1)//self.block+1):
                if index not in self.cache:
                    a=index*self.block;b=min(a+self.block,self.size)-1
                    r=requests.get(self.url,params=self.params,headers={'Range':f'bytes={a}-{b}'},timeout=(20,60))
                    r.raise_for_status();assert r.status_code==206,(r.status_code,r.headers)
                    self.cache[index]=r.content;self.calls+=1
                    print('RANGE',a,b,'calls',self.calls,flush=True)
                v=self.cache[index];a=max(start-index*self.block,0);b=min(end-index*self.block,len(v));parts.append(v[a:b])
            data=b''.join(parts)
        self.pos=end;return data
    def readinto(self,b):
        data=self.read(len(b));b[:len(data)]=data;return len(data)

if __name__=='__main__':
    f=HTTPFile()
    with h5py.File(f,'r')as h:
        print('ATTRS',{k:str(v)for k,v in h.attrs.items()},flush=True)
        for k,v in h.items():
            print('VARIABLE',k,v.shape,str(v.dtype),'chunks',v.chunks,'attrs',{a:str(b)for a,b in v.attrs.items()if a not in ['DIMENSION_LIST','REFERENCE_LIST']},flush=True)
            if v.ndim==1 and v.shape[0]<15000:print('FIRSTLAST',k,v[:3],v[-3:],flush=True)
