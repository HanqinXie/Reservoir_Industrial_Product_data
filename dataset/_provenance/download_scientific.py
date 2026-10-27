import concurrent.futures, hashlib, json, pathlib, requests, shutil, stat, sys, threading, time, zipfile, re
from datetime import datetime, timezone

sys.stdout.reconfigure(encoding='utf-8')
ROOT = pathlib.Path(__file__).resolve().parents[1]
DISC = ROOT / '_provenance' / 'scientific_discovery'
LOCK = threading.Lock()
RESULTS = []
MANIFEST_NAME = sys.argv[2] if len(sys.argv) > 2 else 'manifest_scientific.json'
LOG_LOCK = threading.Lock()
PROGRESS = {}
STOP_LOG = threading.Event()

def progress_log():
    last = 0
    while not STOP_LOG.wait(30):
        with LOG_LOCK:
            vals = list(PROGRESS.items())
        total = sum(x[1][0] for x in vals)
        print('PROGRESS', stamp(), 'active=', [(k, round(v[0]/1e6,1), round(v[1]/1e6,1)) for k,v in vals], 'active_MB=',round(total/1e6,1),flush=True)

def segmented_download(task, partial, result):
    # The already downloaded prefix is preserved; each new range is explicitly validated.
    with requests.get(task['source_url'], headers={'Range':'bytes=0-0'}, stream=True, timeout=(40,60)) as r:
        r.raise_for_status()
        match = re.fullmatch(r'bytes 0-0/(\d+)', r.headers.get('Content-Range',''))
        if r.status_code != 206 or not match: return False
        size = int(match.group(1))
        result['range_probe'] = {'status_code':r.status_code, 'content_range':r.headers.get('Content-Range'), 'validated':True}
    if task.get('expected_bytes') and size != task['expected_bytes']: raise ValueError('Range total differs from official metadata')
    task['expected_bytes'] = size
    prefix = partial.stat().st_size if partial.exists() else 0
    if prefix > size: raise ValueError('Existing partial is longer than file')
    segments = partial.with_suffix(partial.suffix+'.segments')
    segments.mkdir(parents=True, exist_ok=True)
    span = 32*1024*1024
    ranges = [(s,min(s+span-1,size-1)) for s in range(prefix,size,span)]
    done = prefix
    dlock = threading.Lock()
    key = task['id']+' '+task['name']
    with LOG_LOCK: PROGRESS[key]=(done,size)
    def get_range(pair):
        nonlocal done
        start,end=pair; f=segments/(str(start)+'-'+str(end)+'.bin')
        if f.exists() and f.stat().st_size == end-start+1:
            with dlock: done+=f.stat().st_size
            with LOG_LOCK: PROGRESS[key]=(done,size)
            return f
        fp=f.with_suffix('.tmp')
        for attempt in range(5):
            try:
                have=fp.stat().st_size if fp.exists() else 0
                if have > end-start+1: fp.unlink();have=0
                reqstart=start+have
                if reqstart<=end:
                    with requests.get(task['source_url'], headers={'Range':f'bytes={reqstart}-{end}'},stream=True,timeout=(40,45)) as r:
                        r.raise_for_status()
                        cr=f'bytes {reqstart}-{end}/{size}'
                        if r.status_code!=206 or r.headers.get('Content-Range')!=cr: raise ValueError('Range response mismatch: '+str(r.status_code)+' '+r.headers.get('Content-Range',''))
                        started=time.monotonic(); received=0
                        with fp.open('ab' if have else 'wb') as dst:
                            for b in r.iter_content(1024*1024):
                                if b:
                                    dst.write(b); received+=len(b)
                                    elapsed=time.monotonic()-started
                                    if elapsed>90 and received/elapsed<128*1024:
                                        raise TimeoutError('Range connection averaged below 128 KiB/s for over 90 seconds; resuming with a fresh connection')
                if fp.stat().st_size != end-start+1: raise ValueError('Range size mismatch')
                fp.replace(f)
                with dlock: done+=f.stat().st_size
                with LOG_LOCK: PROGRESS[key]=(done,size)
                return f
            except Exception as exc:
                if attempt==4:raise
                print('RANGE_RETRY',task['id'],task['name'],start,end,'attempt',attempt+1,type(exc).__name__,str(exc),flush=True)
                time.sleep(2*(attempt+1))
    with concurrent.futures.ThreadPoolExecutor(max_workers=task.get('range_workers',8)) as pool: list(pool.map(get_range,ranges))
    with partial.open('ab') as dst:
        for start,end in ranges:
            f=segments/(str(start)+'-'+str(end)+'.bin')
            with f.open('rb') as src: shutil.copyfileobj(src,dst,4*1024*1024)
            f.unlink()
    segments.rmdir()
    if partial.stat().st_size!=size:raise ValueError('Assembled file size mismatch')
    with LOG_LOCK: PROGRESS.pop(key,None)
    return True

def stamp(): return datetime.now(timezone.utc).isoformat()
def save(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + '.tmp')
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
    tmp.replace(path)
def digest(path):
    sha, md5 = hashlib.sha256(), hashlib.md5()
    with path.open('rb') as f:
        for b in iter(lambda: f.read(4*1024*1024), b''): sha.update(b); md5.update(b)
    return sha.hexdigest(), md5.hexdigest()
def _zip_utf8_name(info):
    """Recover unflagged UTF-8 Chinese names without guessing legacy encodings."""
    if info.flag_bits & 0x800 or info.filename.isascii(): return info.filename
    try: decoded = info.filename.encode('cp437').decode('utf-8')
    except (UnicodeEncodeError, UnicodeDecodeError): return info.filename
    return decoded if any('\u3400' <= char <= '\u9fff' for char in decoded) else info.filename

def _is_macos_metadata(name):
    parts = pathlib.PurePosixPath(name.replace('\\', '/')).parts
    return bool(parts) and ('__MACOSX' in parts or parts[-1] == '.DS_Store' or parts[-1].startswith('._'))

def extract_zip(path, dest):
    dest.mkdir(parents=True, exist_ok=True)
    base = dest.resolve()
    members, plan, renamed, skipped = [], [], [], []
    windows_d01 = path.parent.name.startswith('D01_')
    prefix_map, target_map, kinds, files_seen = {}, {}, {}, set()
    reserved = {'CON','PRN','AUX','NUL'} | {f'COM{i}' for i in range(1,10)} | {f'LPT{i}' for i in range(1,10)}
    with zipfile.ZipFile(path) as z:
        for info in z.infolist():
            name = (_zip_utf8_name(info) if windows_d01 else info.filename).replace('\\', '/')
            pp = pathlib.PurePosixPath(name)
            if pp.is_absolute() or '..' in pp.parts or re.match(r'^[A-Za-z]:',name):
                raise ValueError('Unsafe archive member: ' + name)
            if stat.S_ISLNK((info.external_attr >> 16) & 0xFFFF):
                raise ValueError('Archive link rejected: ' + name)
            if windows_d01 and _is_macos_metadata(name):
                if not info.is_dir():
                    skipped.append({'original_member': info.filename, 'byte_size': info.file_size,
                                    'sha256': hashlib.sha256(z.read(info)).hexdigest(),
                                    'reason': 'macOS metadata; retained in original data.zip'})
                continue
            if not pp.parts: continue
            for idx,part in enumerate(pp.parts):
                raw_prefix=tuple(pp.parts[:idx+1]); kind='directory' if idx<len(pp.parts)-1 or info.is_dir() else 'file'
                if raw_prefix in prefix_map:
                    if kinds[raw_prefix]!=kind:raise ValueError('Archive file/directory conflict: '+name)
                    continue
                safe_part=re.sub(r'[<>:"|?*\x00-\x1f]','_',part).rstrip(' .') or '_'
                if safe_part.split('.')[0].upper() in reserved:safe_part='_'+safe_part
                parent=prefix_map.get(tuple(pp.parts[:idx]),())
                proposed=parent+(safe_part,);key='/'.join(proposed).casefold()
                if key in target_map and target_map[key]!=raw_prefix:
                    suffix=hashlib.sha256('/'.join(raw_prefix).encode('utf-8')).hexdigest()[:10]
                    ext=pathlib.PurePosixPath(safe_part).suffix if kind=='file' else ''
                    safe_part=(safe_part[:-len(ext)] if ext else safe_part)+'__'+suffix+ext
                    proposed=parent+(safe_part,);key='/'.join(proposed).casefold()
                    if key in target_map:raise ValueError('Unresolvable case-insensitive filename collision: '+name)
                prefix_map[raw_prefix]=proposed;target_map[key]=raw_prefix;kinds[raw_prefix]=kind
            safe_parts=prefix_map[tuple(pp.parts)]
            target = (base / pathlib.Path(*safe_parts)).resolve()
            if not target.is_relative_to(base): raise ValueError('Path escape rejected')
            if not info.is_dir():
                if tuple(pp.parts) in files_seen:raise ValueError('Duplicate archive file member rejected: '+name)
                files_seen.add(tuple(pp.parts))
            if tuple(pathlib.PurePosixPath(info.filename.replace('\\', '/')).parts)!=safe_parts:renamed.append({'original_member':info.filename,'decoded_member':name,'extracted_path':str(target.relative_to(ROOT))})
            plan.append((info,target))
        for info,target in plan:
            if info.is_dir(): target.mkdir(parents=True, exist_ok=True); continue
            target.parent.mkdir(parents=True, exist_ok=True)
            sha = hashlib.sha256()
            with z.open(info) as src, target.open('wb') as dst:
                for b in iter(lambda: src.read(4*1024*1024), b''): dst.write(b); sha.update(b)
            members.append({'original_member':info.filename,'path': str(target.relative_to(ROOT)), 'byte_size': target.stat().st_size, 'sha256': sha.hexdigest()})
    result = {'status': 'extracted_verified_crc', 'path': str(dest.relative_to(ROOT)), 'member_count': len(members), 'uncompressed_bytes': sum(x['byte_size'] for x in members), 'renamed_member_count':len(renamed),'renamed_members':renamed,'members': members}
    if windows_d01:
        result.update(skipped_member_count=len(skipped), skipped_members=skipped,
                      archive_file_member_count=len(members)+len(skipped),
                      archive_uncompressed_bytes=sum(x['byte_size'] for x in members+skipped),
                      windows_policy='Recover unflagged UTF-8 Chinese filenames; omit macOS metadata only; preserve research bytes.')
    return result

def run_task(task):
    folder = ROOT / task['directory']; folder.mkdir(parents=True, exist_ok=True)
    out = folder / task['name']; partial = out.with_suffix(out.suffix + '.part')
    result = {**task, 'started_utc': stamp()}
    try:
        if not out.exists():
            if task.get('expected_bytes',0) is None or task.get('expected_bytes',0) >= 50*1024*1024:
                if segmented_download(task,partial,result): partial.replace(out)
        if not out.exists():
            for attempt in range(4):
                try:
                    offset = partial.stat().st_size if partial.exists() else 0
                    headers = {'Range': f'bytes={offset}-'} if offset else {}
                    with requests.get(task['source_url'], headers=headers, stream=True, timeout=(40,120)) as r:
                        r.raise_for_status()
                        if 'text/html' in r.headers.get('Content-Type', '').lower(): raise ValueError('HTML response rejected as data')
                        mode = 'ab' if offset and r.status_code == 206 else 'wb'
                        if mode == 'wb': offset = 0
                        result['resolved_url'] = r.url
                        result['content_type'] = r.headers.get('Content-Type')
                        with partial.open(mode) as f:
                            for b in r.iter_content(4*1024*1024):
                                if b: f.write(b)
                    if task.get('expected_bytes') and partial.stat().st_size != task['expected_bytes']:
                        raise ValueError(f"Size mismatch {partial.stat().st_size} != {task['expected_bytes']}")
                    partial.replace(out); break
                except Exception:
                    if attempt == 3: raise
                    time.sleep(2*(attempt+1))
        sha, md5 = digest(out)
        if task.get('expected_bytes') and out.stat().st_size != task['expected_bytes']: raise ValueError('Final size mismatch')
        if task.get('expected_md5') and md5 != task['expected_md5']: raise ValueError('Official MD5 mismatch')
        result.update(status='downloaded', path=str(out.relative_to(ROOT)), byte_size=out.stat().st_size, sha256=sha, md5=md5, official_md5_verified=bool(task.get('expected_md5')))
        print('DOWNLOADED', task['id'], task['name'], out.stat().st_size, flush=True)
        if out.suffix.lower() == '.zip':
            result['extraction'] = extract_zip(out, folder / 'extracted' / out.stem)
            if result['extraction'].get('renamed_members'):
                save(folder/'_provenance'/(out.name+'.filename_mapping.json'),result['extraction']['renamed_members'])
            result['status'] = 'downloaded_and_extracted'
            print('EXTRACTED', task['id'], task['name'], result['extraction']['member_count'], flush=True)
    except Exception as exc:
        result.update(status='failed', error=f'{type(exc).__name__}: {exc}')
        print('FAILED', task['id'], task['name'], str(exc), flush=True)
    result['finished_utc'] = stamp()
    with LOCK:
        RESULTS.append(result)
        save(ROOT / '_provenance' / MANIFEST_NAME, {'generated_utc':stamp(), 'policy':'Original archives retained. ZIP member paths validated; links rejected. No downloaded code executed; no pickle deserialization.', 'files': RESULTS})
        save(folder / '_provenance' / (task['name'] + '.manifest.json'), result)
    return result

def main():
    tasks=json.loads((ROOT/'_provenance'/(sys.argv[1] if len(sys.argv)>1 else 'scientific_tasks.json')).read_text(encoding='utf-8'))
    threading.Thread(target=progress_log,daemon=True).start()
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
        fs=[pool.submit(run_task,t) for t in tasks]
        for f in concurrent.futures.as_completed(fs): f.result()
    STOP_LOG.set()
    print('ALL FINISHED',len(RESULTS),'failed',sum(r['status']=='failed' for r in RESULTS),flush=True)
if __name__=='__main__':main()
