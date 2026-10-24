import sys,collections,datetime as dt; sys.path.insert(0,sys.argv[1]); import sim
d=sim.load(sys.argv[2])
feb=d['feb']; print('feb rows',len(feb),'mapped',sum(r['key'] is not None for r in feb),'circuits',len({r['c7'] for r in feb if r['key']}))
# ARCOS calibration
ar=[(r['fix']-r['rep']).days for r in feb if r['repaired'] and r['fix']!=dt.date(2024,10,22)]
def dist(v):
    n=len(v);c=collections.Counter(min(x,3) for x in v); return 'n=%d P10/50/90=%s mean=%.2f  d0 %.0f%% d1 %.0f%% d2 %.0f%% d3+ %.0f%%'%(n,sim.pct(v),sum(v)/n,*(100*c[k]/n for k in range(4)))
print('ARCOS days',dist(ar)); arc=[min(x,10) for x in ar]; print('ARCOS capped10 mean %.2f'%(sum(arc)/len(arc)))
for mode,n in [('circuit',1),('circuit',2),('circuit',3),('pool',10),('pool',20),('pool',40),('pool',80)]:
    jobs=sim.run(d,sim.make_jobs(d,seed=7),mode,n)
    sd=[int(j['fin']//24)-int(j['rel']//24) for j in jobs if j['r']['repaired'] and j['r']['fix']!=dt.date(2024,10,22)]
    hrs=[j['fin']-j['rel'] for j in jobs]
    ho=sim.home_outages(d,jobs)
    ev=[]
    for _,u,_ in ho:
        for a,b in u: ev+= [(a,1),(b,-1)]
    ev.sort(); cur=pk=0; pt=None
    for t,x in ev:
        cur+=x
        if cur>pk: pk,pt=cur,t
    tot=[sum(b-a for a,b in u) for _,u,_ in ho]
    last=max(j['fin'] for j in jobs)
    print(f'{mode}{n}: homes_out={len(ho)} peak={pk} at t={pt:.1f}h | home dur P10/50/90={sim.pct(tot)} | job rep->fix h P10/50/90={sim.pct(hrs)} | sim days {dist(sd)} | last fix t={last:.0f}h')
