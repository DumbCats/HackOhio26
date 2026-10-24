# Build proto data: homes (hashed) with path keys, damage rows with device keys + base hours.
import sys,re,math,collections,json,hashlib,pickle,datetime as dt
R=sys.argv[1]; sys.path.insert(0,R); import lib
E=R+'/ex/'; OUT=sys.argv[2]; XW=sys.argv[3]
X={int(k):v for k,v in json.load(open(XW))['map'].items()}   # 7digit -> CIR num
INV={v:k for k,v in X.items()}
SALT=b'proto-salt-not-secret'
def load(L,keep):
    _,rows=lib.read(E+L+'.dbf',keep);_,_,p=lib.shp(E+L+'.shp')
    for r,q in zip(rows,p): r['xy']=q
    return rows
_,cust=lib.read(E+'Customer_Clip.dbf',{'premise_nu','circuit_id','kind_of_se','critical_c'})
cinfo={r['premise_nu']:r for r in cust}
homes=[]; down=collections.Counter(); first_iso={}; depth={}
for line in open(E+'matched_upstream.txt',encoding='latin1'):
    t=line.rstrip('\r\n').split('\t'); toks=[x.split('*') for x in t[1:]]
    if len(toks)<2: continue
    c7=int(toks[-1][3]); cb='CB:%d'%c7
    keys=[y[3] for y in toks[:-1]]+[cb]
    for i,k in enumerate(keys):
        down[k]+=1
        d=len(keys)-1-i   # 0 = breaker
        depth[k]=min(depth.get(k,99),d)
    iso=[y[3] for y in toks[1:-1] if y[0]=='eo_isolating_eqpt_inst']
    first_iso[toks[0][3]]=iso[0] if iso else cb
    ci=cinfo.get(t[0])
    homes.append(dict(hid=hashlib.sha256(SALT+t[0].encode()).hexdigest()[:10],c7=c7,
        oh=(ci or {}).get('kind_of_se')=='Overhead', keys=keys))
# customers per circuit (all customers, even w/o chain)
ccount=collections.Counter(int(r['circuit_id']) for r in cust)
lay={}
for L,k in [('Transformer_Clip','T'),('Fuse_Bank_Clip','F'),('Recloser_Bank_Clip','R')]:
    rows=load(L,{'circuit_id','location_n'}); by=collections.defaultdict(list)
    for r in rows:
        if down[r['location_n']]>0: by[int(r['circuit_id'])].append(r)
    lay[k]=by
def m(a,b): return math.hypot((a[0]-b[0])*88000,(a[1]-b[1])*111000)
def nearest(k,c,xy):
    best=(1e12,None)
    for r in lay[k].get(c,[]):
        d=m(xy,r['xy'])
        if d<best[0]: best=(d,r)
    return best
HRS={'primary':1.129,'':1.129,'Pole':4.812,'Fuse Bank':1.240,'secondary':0.879,'Transformer':3.234,
     'Recloser Bank':1.954,'Switch':2.768,'Capacitor Bank':2.008,'Light':0.872,'Step Transformer':3.200}
A=load('arcos_prod_damage_09_28_Clip',{'Circuit','Asset_Type','Report_Tim','Repaired','Repaired_D','Access_Iss','Special_Eq'})
D=lambda s: dt.date(int(s[:4]),int(s[4:6]),int(s[6:]))
dmg=[]; C=collections.Counter()
rule={'Transformer':'T','secondary':'T','Fuse Bank':'F','Recloser Bank':'R'}
for i,a in enumerate(A):
    mm=re.fullmatch(r'CIR(\d+)',a['Circuit']); cir=int(mm.group(1)) if mm else None
    c7=INV.get(cir) if cir is not None else None
    h=HRS.get(a['Asset_Type'],1.129)+(0.5 if a['Access_Iss']=='Yes' else 0)+{'Backyard Bucket':0.5,'Track Hoe':1.312,'Yard Dog':1.312}.get(a['Special_Eq'],0)
    rec=dict(i=i,cir=cir,c7=c7,asset=a['Asset_Type'],rep=D(a['Report_Tim']),fix=D(a['Repaired_D']) if a['Repaired_D'] else None,
             repaired=a['Repaired']=='Yes',base=h*4.5,key=None)
    if c7 is None or not lay['T'].get(c7): C['unmapped']+=1; dmg.append(rec); continue
    k=rule.get(a['Asset_Type'],'T'); d,r=nearest(k,c7,a['xy'])
    if r is None: k='T'; d,r=nearest('T',c7,a['xy'])
    loc=r['location_n']
    key = loc if (a['Asset_Type'] in ('Transformer','secondary') or k in 'FR') else first_iso.get(loc)
    rec['key']=key; rec['dist']=d; C['mapped']+=1; dmg.append(rec)
print(C, 'homes',len(homes))
pickle.dump(dict(homes=homes,dmg=dmg,down=dict(down),depth=depth,ccount=dict(ccount),X=X),open(OUT,'wb'))
