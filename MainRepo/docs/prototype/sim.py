import pickle,random,math,heapq,collections,datetime as dt
T0=dt.date(2025,2,13)
def load(p):
    d=pickle.load(open(p,'rb'))
    d['feb']=[r for r in d['dmg'] if dt.date(2025,2,12)<=r['rep']<=dt.date(2025,2,18)]
    return d
def pct(v,qs=(10,50,90)):
    v=sorted(v); n=len(v)
    return [round(v[min(n-1,int(q/100*(n-1)+0.5))],2) for q in qs] if n else None
def schedule(jobs,ncrews,t_start=None):
    """jobs: list of dict(rel,dur,pri); returns finish list aligned. greedy list scheduling."""
    order=sorted(range(len(jobs)),key=lambda j:jobs[j]['rel'])
    fin=[None]*len(jobs); avail=[]; crews=[t_start if t_start is not None else -1e9]*ncrews; heapq.heapify(crews); p=0
    left=len(jobs)
    while left:
        T=heapq.heappop(crews)
        while p<len(order) and jobs[order[p]]['rel']<=T:
            j=order[p]; heapq.heappush(avail,(jobs[j]['pri'],j)); p+=1
        if not avail:
            T=jobs[order[p]]['rel']
            while p<len(order) and jobs[order[p]]['rel']<=T:
                j=order[p]; heapq.heappush(avail,(jobs[j]['pri'],j)); p+=1
        _,j=heapq.heappop(avail); s=max(T,jobs[j]['rel']); fin[j]=s+jobs[j]['dur']; left-=1
        heapq.heappush(crews,fin[j])
    return fin
def make_jobs(d,seed=1,sigma=0.35):
    rnd=random.Random(seed); jobs=[]
    for r in d['feb']:
        if r['key'] is None: continue
        rel=(r['rep']-T0).days*24+rnd.random()*24
        dur=r['base']*math.exp(rnd.gauss(0,sigma))
        jobs.append(dict(r=r,rel=rel,dur=dur,c7=r['c7'],pri=(d['depth'].get(r['key'],99),-d['down'].get(r['key'],0),rel)))
    return jobs
def run(d,jobs,mode,n):
    if mode=='circuit':
        by=collections.defaultdict(list)
        for j in jobs: by[j['c7']].append(j)
        for js in by.values():
            for j,f in zip(js,schedule(js,n)): j['fin']=f
    else:
        for j,f in zip(jobs,schedule(jobs,n)): j['fin']=f
    return jobs
def home_outages(d,jobs):
    bykey=collections.defaultdict(list)
    for j in jobs: bykey[j['r']['key']].append(j)
    res=[]
    for hi,h in enumerate(d['homes']):
        js=[j for k in h['keys'] for j in bykey.get(k,())]
        if not js: continue
        iv=sorted((j['rel'],j['fin']) for j in js); u=[]
        for a,b in iv:
            if u and a<=u[-1][1]: u[-1][1]=max(u[-1][1],b)
            else: u.append([a,b])
        res.append((hi,u,len(js)))
    return res
