import sys,collections,math,random,time,datetime as dt,pickle; sys.path.insert(0,sys.argv[1]); import sim
exec(open(sys.argv[1]+'/share.py').read().split('for N in (120')[0].split('d=sim.load')[1].join(['d=sim.load','']) if False else '')
d=sim.load(sys.argv[2]); X=d['X']; T=3.0; N=150
src=open(sys.argv[1]+'/share.py').read(); ns={'sim':sim,'d':d,'collections':collections,'math':math,'random':random,'dt':dt,'T':T,'X':X}
exec(src[src.index('def share_run'):src.index('for N in (120')],ns); exec(src[src.index('def mc'):src.index('rows=[]')],ns)
share_run,mc=ns['share_run'],ns['mc']
good=pickle.load(open(sys.argv[1]+'/good.pkl','rb'))
for g in [good[0],good[1]]:
    jobs=sim.make_jobs(d,seed=g['seed']); K=share_run(jobs,N); h=d['homes'][g['hi']]; c7=h['c7']; circ=[j for j in jobs if j['c7']==c7]; path=set(h['keys'])
    print(g['hid'],g['cir'],'seed',g['seed'],'K',K[c7],'open jobs on circuit',sum(j['fin']>T for j in circ),'replay out',g['out'])
    for lab,kw in [('base',{}),('crews+2',dict(K=K[c7]+2)),('crews=1',dict(K=1)),('access',dict(access=True)),('extra+1',dict(extra=1,h=h))]:
        k=kw.pop('K',K[c7]); print('  ',lab,mc(circ,path,k,n=300,**kw))
    t0=time.time(); mc(circ,path,K[c7],n=1000); print('   1000 sims %.3fs'%(time.time()-t0))
# risk
cc=d['ccount']; dm=[r for r in d['dmg'] if r['c7'] is not None]
feb=collections.Counter(r['c7'] for r in dm if dt.date(2025,2,12)<=r['rep']<=dt.date(2025,2,18))
sep=collections.Counter(r['c7'] for r in dm if dt.date(2024,9,26)<=r['rep']<=dt.date(2024,10,2))
allp=collections.Counter(r['c7'] for r in dm)
H=sum(cc.values())
def band(score):
    cs=sorted(cc,key=lambda c:-score[c]); cum=0; b={}
    for c in cs:
        frac=cum/H; b[c]='High' if frac<0.15 else 'Medium' if frac<0.40 else 'Low'; cum+=cc[c]
    return b
sc={c:1000*(feb[c]+sep[c])/cc[c] for c in cc}; b=band(sc)
cnt=collections.Counter(); 
for c in cc: cnt[b[c]]+=cc[c]
print('A5 bands on (Feb+Sep)/1k homes: homes',dict(cnt),'circuits',dict(collections.Counter(b.values())),'circuits score==0',sum(1 for c in cc if sc[c]==0),'homes',sum(cc[c] for c in cc if sc[c]==0))
print('score per1k P50/P90/max',sim.pct(list(sc.values()),(50,90,100)))
sf={c:1000*feb[c]/cc[c] for c in cc}; bf=band(sf); S=sum(sep.values())
for lab in ('High','Medium','Low'):
    hs=sum(cc[c] for c in cc if bf[c]==lab); ss=sum(sep[c] for c in cc if bf[c]==lab)
    print(f'Feb-only band {lab}: {hs/H:.0%} of homes, {ss}/{S} = {ss/S:.0%} of Sept damage, Sept per1k {1000*ss/hs:.2f}')
fr={c:feb[c] for c in cc}; br=band(fr); ss=sum(sep[c] for c in cc if br[c]=='High'); print('Feb raw-count High: Sept share %.0f%%'%(100*ss/S))
# rank corr (spearman) circuit level
cs=list(cc)
def rk(v):
    o=sorted(range(len(v)),key=lambda i:v[i]); r=[0]*len(v); i=0
    while i<len(o):
        j=i
        while j+1<len(o) and v[o[j+1]]==v[o[i]]: j+=1
        for k in range(i,j+1): r[o[k]]=(i+j)/2
        i=j+1
    return r
a=rk([sf[c] for c in cs]); bb=rk([1000*sep[c]/cc[c] for c in cs]); ma=sum(a)/len(a); mb=sum(bb)/len(bb)
print('spearman Feb/1k vs Sep/1k over',len(cs),'circuits: %.2f'%(sum((x-ma)*(y-mb) for x,y in zip(a,bb))/math.sqrt(sum((x-ma)**2 for x in a)*sum((y-mb)**2 for y in bb))))
print('circuits with Sept damage',sum(1 for c in cc if sep[c]),'with Feb',sum(1 for c in cc if feb[c]),'both',sum(1 for c in cc if sep[c] and feb[c]))
print('A6 <3 past dmg: circuits',sum(1 for c in cc if allp[c]<3),'homes',sum(cc[c] for c in cc if allp[c]<3),'; homes in High band that are A6-Low',sum(cc[c] for c in cc if allp[c]<3 and b[c]=='High'))
lowc=[c for c in cc if allp[c]<3 and cc[c]>200]; rnd=random.Random(5); c=rnd.choice(lowc)
hs=[h for h in d['homes'] if h['c7']==c]; h=rnd.choice(hs); print('FALLBACK',h['hid'],'CIR%d'%X[c],'past dmg',allp[c],'homes',cc[c],'path devices',len(h['keys']),'overhead',h['oh'],'; fallback circuits w/ >200 homes',len(lowc))
