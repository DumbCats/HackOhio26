import sys,collections,math,random,pickle; sys.path.insert(0,sys.argv[1]); import sim
d=sim.load(sys.argv[2]); src=open(sys.argv[1]+'/share.py').read(); ns={'sim':sim,'d':d,'collections':collections}
exec(src[src.index('def share_run'):src.index('def stats')],ns)
for s in (7,8):
    jobs=sim.make_jobs(d,seed=s); ns['share_run'](jobs,150); print('share150 seed',s,'job rep->fix h P10/50/90',sim.pct([j['fin']-j['rel'] for j in jobs]))
g=pickle.load(open(sys.argv[1]+'/good.pkl','rb'))[1]
jobs=sim.make_jobs(d,seed=g['seed']); K=ns['share_run'](jobs,150); h=d['homes'][g['hi']]; circ=[j for j in jobs if j['c7']==h['c7']]; path=set(h['keys'])
def mc(T,known,n=300,seed=42):
    rnd=random.Random(seed); res=[]
    op=[j for j in circ if j['fin']>T and (j['rel']<=T or not known)]
    for _ in range(n):
        js=[dict(rel=max(T,j['rel']),dur=j['r']['base']*math.exp(rnd.gauss(0,.35)),pri=j['pri'],on=j['r']['key'] in path) for j in op]
        f=sim.schedule(js,K[h['c7']],t_start=T); res.append(T+max([x for x,j in zip(f,js) if j['on']],default=T)-T)
    return sim.pct(res)
for T in (4.5,9.0,10.0,14.0):
    print('t=%.1f known-only restore at t P10/50/90'%T,mc(T,True),'| all-unfixed',mc(T,False))
