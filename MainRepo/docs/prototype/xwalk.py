import sys,re,collections,json;sys.path.insert(0,sys.argv[1]);import lib
E=sys.argv[1]+'/ex/'
def numc(s):
    m=re.fullmatch(r'[A-Z]*(\d+)',s or ''); return int(m.group(1)) if m else None
pairs=collections.Counter()
for L in ['Transformer_Clip','Fuse_Bank_Clip','Recloser_Bank_Clip','Switch_Clip']:
    _,T=lib.read(E+L+'.dbf',{'circuit_id','aep_circui'})
    for r in T:
        a=numc(r['aep_circui'])
        if a is not None: pairs[(int(r['circuit_id']),a)]+=1
fwd=collections.defaultdict(set);inv=collections.defaultdict(set)
for (c,a) in pairs: fwd[c].add(a); inv[a].add(c)
print('fwd multi',{k:v for k,v in fwd.items() if len(v)>1}); print('inv multi',{k:v for k,v in inv.items() if len(v)>1})
diff={c:min(a) for c,a in fwd.items() if a!={c}}
print('non-identity circuit_id->CIR',sorted(diff.items()))
json.dump({str(c):sorted(a) for c,a in fwd.items()},open(sys.argv[1]+'/circuit_xwalk.json','w'))
_,C=lib.read(E+'Customer_Clip.dbf',{'circuit_id','critical_c'}); cc=collections.Counter(int(r['circuit_id']) for r in C)
cust_cir=collections.Counter()
nomap=0
for c,n in cc.items():
    if c in fwd: cust_cir[min(fwd[c])]+=n
    else: nomap+=n
print('customer circuits',len(cc),'without xwalk',nomap,'customer CIR numbers',len(cust_cir))
_,A=lib.read(E+'arcos_prod_damage_09_28_Clip.dbf',{'Circuit','Report_Tim'})
ac=collections.Counter(r['Circuit'] for r in A)
match=[k for k in ac if k.startswith('CIR') and numc(k) in cust_cir]
print('arcos distinct',len(ac),'CIR distinct',sum(1 for k in ac if k.startswith('CIR')),'matched via xwalk',len(match),'rows',sum(ac[k] for k in match))
print('unmatched CIR',[(k,ac[k]) for k in ac if k.startswith('CIR') and numc(k) not in cust_cir])
feb=[r for r in A if '20250213'<=r['Report_Tim']<='20250217']
fc=set(numc(r['Circuit']) for r in feb if r['Circuit'].startswith('CIR'))
inv1={min(a):c for c,a in fwd.items()}
fcs={c for c,a in fwd.items() if min(a) in fc}
print('feb CIR circuits',len(fc),'matched',len(fc&set(cust_cir)),'customers',sum(cust_cir[a] for a in fc),'LS',sum(1 for r in C if int(r['circuit_id']) in fcs and r['critical_c']!='N/A'))
