import sys,collections,datetime as dt,math; sys.path.insert(0,sys.argv[1]); import sim
d=sim.load(sys.argv[2])
j0=sim.make_jobs(d,seed=7); durs=[j['dur'] for j in j0]
print('jobs',len(j0),'job hours P10/50/90',sim.pct(durs),'mean %.1f total crew-h %.0f'%(sum(durs)/len(durs),sum(durs)))
pc=collections.Counter(j['c7'] for j in j0); ch=collections.defaultdict(float)
for j in j0: ch[j['c7']]+=j['dur']
print('jobs/circuit P50/90/max',sim.pct(list(pc.values()),(50,90,100)),'crew-h/circuit P50/90/max',sim.pct(list(ch.values()),(50,90,100)))
print('reports by day',sorted(collections.Counter((j['r']['rep']-sim.T0).days for j in j0).items()))
def ev(mode,n,mult=1.0,seeds=(7,8,9)):
    out=[]
    for s in seeds:
        jobs=sim.make_jobs(d,seed=s)
        for j in jobs: j['dur']*=mult
        if mode=='prop':  # crews per circuit proportional: ceil(jobs/n)
            by=collections.defaultdict(list)
            for j in jobs: by[j['c7']].append(j)
            for js in by.values():
                for j,f in zip(js,sim.schedule(js,max(1,math.ceil(len(js)/n)))): j['fin']=f
        else: sim.run(d,jobs,mode,n)
        sd=[int(j['fin']//24)-int(j['rel']//24) for j in jobs if j['r']['repaired'] and j['r']['fix']!=dt.date(2024,10,22)]
        ho=sim.home_outages(d,jobs); tot=[sum(b-a for a,b in u) for _,u,_ in ho]
        e=[]
        for _,u,_ in ho:
            for a,b in u: e+=[(a,1),(b,-1)]
        e.sort(); cur=pk=0;pt=0
        for t,x in e:
            cur+=x
            if cur>pk: pk,pt=cur,t
        c=collections.Counter(min(x,3) for x in sd); n_=len(sd)
        out.append((sim.pct(sd),sum(sd)/n_,[round(100*c[k]/n_) for k in range(4)],sim.pct(tot),pk,pt,max(j['fin'] for j in jobs)))
    o=out[0]; print(f'{mode}{n} x{mult}: days P10/50/90 {o[0]} mean {o[1]:.2f} d0-3+% {o[2]} | home h P10/50/90 {o[3]} | peak {o[4]} @t={o[5]:.0f} | last {o[6]:.0f}h | mean-days over seeds {[round(x[1],2) for x in out]}')
for k in (3,5,8,12): ev('circuit',k)
for n in (80,120,160,200,250,300): ev('pool',n)
for n in (4,6,8,10): ev('prop',n)
for n in (40,80): ev('pool',n,mult=1/4.5)
