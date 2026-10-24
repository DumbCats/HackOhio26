import sys,collections,math,random,time,datetime as dt,pickle; sys.path.insert(0,sys.argv[1]); import sim
d=sim.load(sys.argv[2]); X=d['X']; T=3.0
feb=collections.Counter(r['c7'] for r in d['feb']); cc=d['ccount']
def share_run(jobs,N):
    ch=collections.defaultdict(float); by=collections.defaultdict(list)
    for j in jobs: ch[j['c7']]+=j['r']['base']; by[j['c7']].append(j)   # expected workload, seed-independent
    tot=sum(ch.values()); K={c:max(1,round(N*ch[c]/tot)) for c in by}
    for c,js in by.items():
        for j,f in zip(js,sim.schedule(js,K[c])): j['fin']=f
    return K
def stats(jobs):
    sd=[int(j['fin']//24)-int(j['rel']//24) for j in jobs if j['r']['repaired'] and j['r']['fix']!=dt.date(2024,10,22)]
    c=collections.Counter(min(x,3) for x in sd); ho=sim.home_outages(d,jobs); tot=[sum(b-a for a,b in u) for _,u,_ in ho]
    e=sorted([(a,1) for _,u,_ in ho for a,b in u]+[(b,-1) for _,u,_ in ho for a,b in u]); cur=pk=pt=0
    for t,x in e:
        cur+=x
        if cur>pk: pk,pt=cur,t
    return sim.pct(sd,(50,90)),[round(100*c[k]/len(sd)) for k in range(4)],sim.pct(tot),pk,round(pt,1),len(ho),ho
for N in (120,140,150,160,200):
    for s in (7,8):
        K=share_run(jobs:=sim.make_jobs(d,seed=s),N); st=stats(jobs)
        print(f'share{N} seed{s}: crews used {sum(K.values())} days P50/90 {st[0]} d0..3+% {st[1]} home h P10/50/90 {st[2]} peak {st[3]} @t={st[4]} homes out {st[5]}')
N=int(sys.argv[3])
def mc(circ,path,K,n=150,access=False,extra=0,seed=42,h=None):
    rnd=random.Random(seed); open_=[j for j in circ if j['fin']>T]; res=[]
    for _ in range(n):
        js=[dict(rel=max(T,j['rel']),dur=j['r']['base']*math.exp(rnd.gauss(0,.35))+(rnd.uniform(2,8) if access else 0),pri=j['pri'],on=j['r']['key'] in path) for j in open_]
        for _ in range(extra):
            k=rnd.choice(h['keys']); js.append(dict(rel=T,dur=4.5*rnd.choice([1.129,1.129,4.812,1.24,0.879])*math.exp(rnd.gauss(0,.35))+(rnd.uniform(2,8) if access else 0),pri=(d['depth'].get(k,99),-d['down'].get(k,0),T),on=True))
        f=sim.schedule(js,K,t_start=T); res.append(max([x for x,j in zip(f,js) if j['on']],default=T)-T)
    return sim.pct(res)
rows=[]; prof=[]
for s in range(1,11):
    jobs=sim.make_jobs(d,seed=s); K=share_run(jobs,N); ho=sim.home_outages(d,jobs)
    bykey=collections.defaultdict(list)
    for j in jobs: bykey[j['r']['key']].append(j)
    seen=set(); n=0
    for hi,u,nj in ho:
        if not(len(u)==1 and 2<=u[0][0]<=6 and 10<=u[0][1]-u[0][0]<=20 and nj>=2): continue
        n+=1; h=d['homes'][hi]; sig=h['keys'][0]
        if sig in seen: continue
        seen.add(sig); c7=h['c7']; circ=[j for j in jobs if j['c7']==c7]
        b=mc(circ,set(h['keys']),K[c7],n=100); up=mc(circ,set(h['keys']),K[c7]+2,n=100)
        js=[j for k in h['keys'] for j in bykey.get(k,())]
        rows.append(dict(seed=s,hid=h['hid'],cir='CIR%d'%X[c7],path=len(h['keys']),dmg_path=nj,feb_c=feb[c7],per1k=round(1000*feb[c7]/cc[c7]),K=K[c7],out=[round(a,1) for a in u[0]],rep=sorted(round(j['rel'],1) for j in js),mc=b,d_up=round(up[1]-b[1],1),oh=h['oh'],hi=hi))
    prof.append(n)
print(f'N={N}: story-profile homes per seed',prof,'unique-transformer candidates',len(rows))
good=[r for r in rows if r['d_up']<=-1 and r['mc'][2]<=30 and any(x>4 for x in r['rep'])]
print('crew-sensitive (+2 crews moves P50 >=1h) with a later path report',len(good),'circuits',sorted({r['cir'] for r in good}))
good.sort(key=lambda r:(abs(r['out'][0]-3)+abs(r['out'][1]-17)))
for r in good[:6]: print({k:v for k,v in r.items() if k!='hi'})
pickle.dump(good,open(sys.argv[1]+'/good.pkl','wb'))
