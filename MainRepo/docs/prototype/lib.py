import struct
def fields(p):
    f=open(p,'rb');h=f.read(32);n,hl,rl=struct.unpack('<IHH',h[4:12]);fs=[]
    while True:
        d=f.read(32)
        if d[0]==0x0D:break
        fs.append((d[:11].split(b'\0')[0].decode(),chr(d[11]),d[16],d[17]))
    return n,fs
def read(p,keep=None):
    f=open(p,'rb');h=f.read(32);n,hl,rl=struct.unpack('<IHH',h[4:12]);fs=[]
    while True:
        d=f.read(32)
        if d[0]==0x0D:break
        fs.append((d[:11].split(b'\0')[0].decode(),chr(d[11]),d[16]))
    f.seek(hl);out=[]
    sl=[];o=1
    for nm,t,l in fs:
        if keep is None or nm in keep: sl.append((nm,o,l))
        o+=l
    for _ in range(n):
        r=f.read(rl)
        out.append({nm:r[o:o+l].decode('latin1').strip() for nm,o,l in sl})
    return fs,out
def shp(p):
    f=open(p,'rb');h=f.read(100);st=struct.unpack('<i',h[32:36])[0];bb=struct.unpack('<4d',h[36:68])
    pts=[]
    while True:
        rh=f.read(8)
        if len(rh)<8:break
        num,cl=struct.unpack('>2i',rh);c=f.read(cl*2);t=struct.unpack('<i',c[:4])[0]
        if t in (1,11,21): pts.append(struct.unpack('<2d',c[4:20]))
        else: pts.append(None)
    return st,bb,pts
