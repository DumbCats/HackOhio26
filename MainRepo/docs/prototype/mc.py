import sys,collections,datetime as dt,math,random,time,heapq,pickle; sys.path.insert(0,sys.argv[1]); import sim
d=sim.load(sys.argv[2]); X=d['X']; POOL=120
# seed robustness of story profile
fit=collections.Counter(); per=[]
for s in range(1,21):
    jobs=sim.run(d,sim.make_jobs(d,seed=s),'pool',POOL); ho=sim.home_outages(d,jobs)
    bykey=collections.defaultdict(list)
    for j in jobs: bykey[j['r']['key']].append(j)
    n=0;cs=set();n2=0
    for hi,u,nj in ho:
        if len(u)==1 and 2<=u[0][0]<=6 and 10<=u[0][1]-u[0][0]<=20 and nj>=2:
            n+=1; cs.add(d['homes'][hi]['c7']); fit[hi]+=1
        if len(u)==1 and 2<=u[0][0]<=6 and 10<=u[0][1]-u[0][0]<=20: n2+=1
    per.append((n,len(cs),n2))
print('story-profile per seed (homes, circuits, homes ignoring 2+jobs): P50/min/max homes',sim.pct([p[0] for p in per],(50,0,100)),'circuits',sim.pct([p[1] for p in per],(50,0,100)),'any-jobs',sim.pct([p[2] for p in per],(50,0,100)))
print('homes fitting in >=1 seed',len(fit))
# MC on story home from seed 7
picks=pickle.load(open(sys.argv[1]+'/picks.pkl','rb')); hi=picks['story'][0]; h=d['homes'][hi]; c7=h['c7']; path=set(h['keys'])
base=sim.run(d,sim.make_jobs(d,seed=7),'pool',POOL)
circ=[j for j in base if j['c7']==c7]
tot_open=sum(j['dur'] for j in base if j['fin']>3); c_open=sum(j['dur'] for j in circ if j['fin']>3)
K=max(1,round(POOL*c_open/tot_open)); print('story circuit share of open crew-h at t=3: %.2f -> K=%d of %d'%(c_open/tot_open,K,POOL))
T=3.0
assets=[r for r in d['feb'] if r['key']]
def mc(n=300,crews=K,access=False,extra=0,known_only=False,seed=42):
    rnd=random.Random(seed); open_=[j for j in circ if j['fin']>T and (j['rel']<=T or not known_only)]
    res=[]
    for _ in range(n):
        js=[]
        for j in open_:
            dur=j['r']['base']*math.exp(rnd.gauss(0,0.35))+(rnd.uniform(2,8) if access else 0)
            js.append(dict(rel=max(T,j['rel']),dur=dur,pri=j['pri'],on=j['r']['key'] in path))
        for _ in range(extra):
            a=rnd.choice(assets); k=rnd.choice(h['keys'])
            js.append(dict(rel=T,dur=a['base']*math.exp(rnd.gauss(0,0.35))+(rnd.uniform(2,8) if access else 0),pri=(d['depth'].get(k,99),-d['down'].get(k,0),T),on=True))
        f=sim.schedule(js,crews,t_start=T)
        res.append(max([x for x,j in zip(f,js) if j['on']],default=T)-T)
    return sim.pct(res)
print('open jobs on circuit at t=3: all',sum(1 for j in circ if j['fin']>T),'known(rel<=3)',sum(1 for j in circ if j['fin']>T and j['rel']<=T))
for ko in (False,True):
    print('known_only' if ko else 'all-unfixed(plan)', 'base',mc(known_only=ko),'crews+2',mc(crews=K+2,known_only=ko),'access',mc(access=True,known_only=ko),'extra+1',mc(extra=1,known_only=ko),'crews=1',mc(crews=1,known_only=ko))
t0=time.time(); mc(n=1000); print('runtime per 1000 sims (all-unfixed, %d jobs): %.2fs'%(sum(1 for j in circ if j['fin']>T),time.time()-t0))
# regional-pool MC (all open region jobs) runtime
openR=[j for j in base if j['fin']>T]
t0=time.time(); rnd=random.Random(1)
for _ in range(50):
    js=[dict(rel=max(T,j['rel']),dur=j['r']['base']*math.exp(rnd.gauss(0,.35)),pri=j['pri']) for j in openR]; sim.schedule(js,POOL,t_start=T)
print('regional MC: %d jobs, est per 1000 sims %.1fs'%(len(openR),(time.time()-t0)*20))
