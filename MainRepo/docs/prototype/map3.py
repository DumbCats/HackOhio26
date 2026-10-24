import sys,re,math,collections;sys.path.insert(0,sys.argv[1]);import lib
E=sys.argv[1]+'/ex/'
import json
INV={v[0]:int(k) for k,v in json.load(open(sys.argv[1]+"/circuit_xwalk.json")).items()}
def num0(s):
    m=re.fullmatch(r'CIR(\d+)',s); return int(m.group(1)) if m else None
def load(L,keep):
    _,rows=lib.read(E+L+'.dbf',keep);_,_,p=lib.shp(E+L+'.shp')
    for r,q in zip(rows,p): r['xy']=q
    return rows
A=load('arcos_prod_damage_09_28_Clip',{'Circuit','Asset_Type','Report_Tim'})
# downstream customer counts per device location from chains
down=collections.Counter(); first_iso={}
for line in open(E+'matched_upstream.txt',encoding='latin1'):
    t=line.rstrip('\r\n').split('\t'); toks=[x.split('*') for x in t[1:]]
    for y in toks[:-1]: down[y[3]]+=1
    iso=[y for y in toks[1:-1] if y[0]=='eo_isolating_eqpt_inst']
    first_iso[toks[0][3]]= iso[0][3] if iso else ('CB',toks[-1][3])
    down[('CB',toks[-1][3])]+=1
lay={}
for L,k in [('Transformer_Clip','T'),('Fuse_Bank_Clip','F'),('Recloser_Bank_Clip','R'),('Switch_Clip','S')]:
    rows=load(L,{'circuit_id','location_n'}); by=collections.defaultdict(list)
    for r in rows: by[int(r['circuit_id'])].append(r)
    lay[k]=by
def m(a,b): return math.hypot((a[0]-b[0])*88000,(a[1]-b[1])*111000)
def nearest(k,c,xy,need_chain=True):
    best=(1e12,None)
    for r in lay[k].get(c,[]):
        if need_chain and down[r['location_n']]==0: continue
        d=m(xy,r['xy'])
        if d<best[0]: best=(d,r)
    return best
dist=collections.defaultdict(list); aff=collections.defaultdict(list); C=collections.Counter()
rule={'Transformer':'T','secondary':'T','Fuse Bank':'F','Recloser Bank':'R','Switch':'S'}
for a in A:
    c=INV.get(num0(a["Circuit"]))
    if c is None or not lay['T'].get(c): C['no_circuit_topology']+=1; continue
    at=a['Asset_Type']; k=rule.get(at,'T')
    d,r=nearest(k,c,a['xy'])
    if r is None: C['no_dev_'+k]+=1; d,r=nearest('T',c,a['xy']); k='T'
    dist[at].append(d)
    if at in ('Transformer','secondary'): n=down[r['location_n']]
    elif k in 'FRS' and k==rule.get(at): n=down[r['location_n']]
    else: n=down[first_iso.get(r['location_n'])]
    aff[at].append(n); C['mapped']+=1
print(C)
def q(v):
    v=sorted(v);n=len(v);return (n,round(v[int(.5*(n-1))]),round(v[int(.9*(n-1))]),round(v[-1]))
for at in dist: print(at,'dist m n/P50/P90/max',q(dist[at]),'affected cust n/P50/P90/max',q(aff[at]))
allD=[d for v in dist.values() for d in v]; n=len(allD)
print('ALL dist within 100m',sum(d<=100 for d in allD)/n,'250m',sum(d<=250 for d in allD)/n,'1km',sum(d<=1000 for d in allD)/n)
