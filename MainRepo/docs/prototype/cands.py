import sys,collections,math,random,time; sys.path.insert(0,sys.argv[1]); import sim
d=sim.load(sys.argv[2]); X=d['X']; POOL=120; T=3.0
feb=collections.Counter(r['c7'] for r in d['feb']); cc=d['ccount']
def mc(circ,path,K,n=150,access=False,extra=0,seed=42,h=None):
    rnd=random.Random(seed); open_=[j for j in circ if j['fin']>T]; res=[]
    for _ in range(n):
        js=[dict(rel=max(T,j['rel']),dur=j['r']['base']*math.exp(rnd.gauss(0,.35))+(rnd.uniform(2,8) if access else 0),pri=j['pri'],on=j['r']['key'] in path) for j in open_]
        for _ in range(extra):
            k=rnd.choice(h['keys']); js.append(dict(rel=T,dur=4.5*rnd.choice([1.129,1.129,4.812,1.24,0.879])*math.exp(rnd.gauss(0,.35)),pri=(d['depth'].get(k,99),-d['down'].get(k,0),T),on=True))
        f=sim.schedule(js,K,t_start=T); res.append(max([x for x,j in zip(f,js) if j['on']],default=T)-T)
    return sim.pct(res)
rows=[]
for s in range(1,21):
    jobs=sim.run(d,sim.make_jobs(d,seed=s),'pool',POOL); ho=sim.home_outages(d,jobs)
    bykey=collections.defaultdict(list)
    for j in jobs: bykey[j['r']['key']].append(j)
    tot_open=sum(j['dur'] for j in jobs if j['fin']>T); seen=set()
    for hi,u,nj in ho:
        if not(len(u)==1 and 2<=u[0][0]<=6 and 10<=u[0][1]-u[0][0]<=20 and nj>=2): continue
        h=d['homes'][hi]; sig=(s,h['keys'][0])
        if sig in seen: continue
        seen.add(sig); c7=h['c7']; circ=[j for j in jobs if j['c7']==c7]
        K=max(1,round(POOL*sum(j['dur'] for j in circ if j['fin']>T)/tot_open))
        b=mc(circ,set(h['keys']),K); up=mc(circ,set(h['keys']),K+2); dn=mc(circ,set(h['keys']),max(1,K//2))
        js=[j for k in h['keys'] for j in bykey.get(k,())]
        rows.append((s,h['hid'],'CIR%d'%X[c7],len(h['keys']),nj,feb[c7],round(1000*feb[c7]/cc[c7]),K,[round(a,1) for a in u[0]],sorted(round(j['rel'],1) for j in js),b,up[1]-b[1],dn[1]-b[1]))
print('candidates (seed,transformer-unique)',len(rows))
import pickle;pickle.dump(rows,open(sys.argv[1]+"/rows.pkl","wb"))
good=[r for r in rows if abs(r[10][1]-(r[8][1]-3))<=3 and r[11]<=-1 and r[10][2]<=30]
print("consistent+crew-sensitive",len(good),"seeds",sorted({r[0] for r in good}),"circuits",sorted({r[2] for r in good}))
rows=sorted(good,key=lambda r:r[11])
for r in rows[:8]: print(r)
print('share with |crews+2 dP50|>=1h',sum(abs(r[11])>=1 for r in rows),'crews/2 dP50>=2h',sum(r[12]>=2 for r in rows))
