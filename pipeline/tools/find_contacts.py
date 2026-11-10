import json,re,html,urllib.request,urllib.parse,concurrent.futures as cf
UA={"User-Agent":"Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/126.0 Safari/537.36"}
def get(u):
    try:
        with urllib.request.urlopen(urllib.request.Request(u,headers=UA),timeout=20) as r: return r.geturl(),r.read().decode('utf-8','replace')
    except Exception as e: return u,''
def txt(s): return re.sub(r'\s+',' ',html.unescape(re.sub(r'<(script|style)[^>]*>.*?</\1>|<[^>]+>',' ',s,flags=re.S)))
ROLE=re.compile(r'Nachhaltigkeits(manager|beauftragt|koordinator|referent)\w*|Klimaschutz(manager|beauftragt)\w*|(Referent|Stabsstelle|Koordinat\w+|Beauftragte\w*|Ansprech\w+)[^.]{0,30}Nachhaltigkeit',re.I)
def work(s):
    base,home=get(s['website'])
    links=[]
    for h,t in re.findall(r'<a[^>]+href="([^"#]+)"[^>]*>(.*?)</a>',home,re.S):
        if re.search(r'nachhaltig|klimaschutz|sustainab',h+' '+t,re.I): links.append(urllib.parse.urljoin(base,h))
    links=list(dict.fromkeys(links))[:3]
    out=[]
    for l in links:
        u,page=get(l); t=txt(page)
        for m in ROLE.finditer(t):
            out.append((u,t[max(0,m.start()-110):m.end()+130]))
    return s['id'],links,out[:4]
d=json.load(open('data/stuwerke.json'))
with cf.ThreadPoolExecutor(8) as ex:
    for sid,links,out in ex.map(work,d):
        print('##',sid,len(links))
        seen=set()
        for u,sn in out:
            k=sn[:60]
            if k in seen: continue
            seen.add(k); print('   ',u[:90]); print('      ',sn[:240])
