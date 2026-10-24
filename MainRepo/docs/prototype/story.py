import sys,collections,datetime as dt,math,random,time,heapq; sys.path.insert(0,sys.argv[1]); import sim
d=sim.load(sys.argv[2]); X=d['X']; POOL=int(sys.argv[3]) if len(sys.argv)>3 else 120
cir=lambda c7:'CIR%d'%X.get(c7,c7)
def share_run(jobs,N):
    ch=collections.defaultdict(float); by=collections.defaultdict(list)
    for j in jobs: ch[j['c7']]+=j['dur']; by[j['c7']].append(j)
    tot=sum(ch.values()); K={}
    for c,js in by.items():
        K[c]=max(1,round(N*ch[c]/tot))
        for j,f in zip(js,sim.schedule(js,K[c])): j['fin']=f
    return K
# calibration check of share mode
for N in (80,120,160):
    jobs=sim.make_jobs(d,seed=7); K=share_run(jobs,N)
    sd=[int(j['fin']//24)-int(j['rel']//24) for j in jobs if j['r']['repaired'] and j['r']['fix']!=dt.date(2024,10,22)]
    c=collections.Counter(min(x,3) for x in sd)
    print(f'share{N}: total crews {sum(K.values())} days P50/90 {sim.pct(sd,(50,90))} d0-3+% {[round(100*c[k]/len(sd)) for k in range(4)]} K per circuit P50/90/max {sim.pct(list(K.values()),(50,90,100))}')
sp=sum(math.ceil(n/10) for n in collections.Counter(j['c7'] for j in sim.make_jobs(d)).values()); print('prop10 total crews',sp)
# replay with regional pool
jobs=sim.run(d,sim.make_jobs(d,seed=7),'pool',POOL)
ho=sim.home_outages(d,jobs)
bykey=collections.defaultdict(list)
for j in jobs: bykey[j['r']['key']].append(j)
# past damage per circuit (all ARCOS rows w/ CIR)
past=collections.Counter(r['c7'] for r in d['dmg'] if r['c7'] is not None)
feb=collections.Counter(r['c7'] for r in d['feb'] if r['c7'] is not None)
sep=collections.Counter(r['c7'] for r in d['dmg'] if r['c7'] is not None and dt.date(2024,9,26)<=r['rep']<=dt.date(2024,10,2))
cc=d['ccount']
story=[];upd=[]
for hi,u,nj in ho:
    if len(u)==1 and 2<=u[0][0]<=6 and 10<=u[0][1]-u[0][0]<=20 and nj>=2:
        story.append(hi)
        h=d['homes'][hi]; js=[j for k in h['keys'] for j in bykey.get(k,())]
        if any(4<=j['rel']<=12 for j in js): upd.append(hi)
print('story-profile homes',len(story),'of which a path job is reported at t 4-12 (estimate-update):',len(upd),'circuits',len({d['homes'][i]['c7'] for i in upd}))
lowc={c for c in cc if past[c]<3}
low=[i for i,h in enumerate(d['homes']) if h['c7'] in lowc]
print('fallback (<3 past dmg) circuits',len(lowc),'of',len(cc),'homes(chain)',len(low),'customers',sum(cc[c] for c in lowc), 'circuits with 0 dmg',sum(1 for c in cc if past[c]==0))
def desc(hi):
    h=d['homes'][hi]; c=h['c7']; js=[j for k in h['keys'] for j in bykey.get(k,())]
    u=[x for i,x,_ in ho if i==hi]
    return dict(id=h['hid'],circuit=cir(c),path_devices=len(h['keys']),dmg_on_path=len(js),dmg_on_circuit_feb=feb[c],
        past_per_1k=round(1000*(feb[c]+sep[c])/cc[c],1),overhead=h['oh'],
        outage=[[round(a,1),round(b,1)] for a,b in u[0]] if u else None,path_job_reported=sorted(round(j['rel'],1) for j in js))
rnd=random.Random(3)
pick=[]
# prefer a story home in upd with out start near 3
upd.sort(key=lambda i:abs([u for k,u,_ in ho if k==i][0][0][0]-3)) if False else None
start={hi:u[0][0] for hi,u,_ in ho}
upd.sort(key=lambda i:abs(start[i]-3))
for hi in upd[:3]: print('STORY',desc(hi))
for hi in rnd.sample(low,2): print('FALLBACK',desc(hi))
import pickle; pickle.dump(dict(story=upd[:3],low=low[:5]),open(sys.argv[1]+'/picks.pkl','wb'))
