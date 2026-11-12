import sys,csv,numpy as np
f=sys.argv[1]; D={}
for r in csv.reader(open(f,encoding="utf-8")):
    if len(r)>=2: D.setdefault(r[1],[]).append(r)
def arr(k,cols):
    rows=[r for r in D.get(k,[]) if all(len(r)>c and r[c]!="" for c in cols)]
    return np.array([[float(r[0])]+[float(r[c]) for c in cols] for r in rows])
aos=arr("aos",[2,3]); ros=arr("ros",[2,3]); dm=arr("dm",[2,3,4]); view=arr("view",[2,3,4,5])
marks=[float(r[0]) for r in D.get("mark",[])]
unw=lambda a: np.degrees(np.unwrap(np.radians(a)))
aos[:,1]=unw(aos[:,1]); ros[:,1]=unw(ros[:,1]); view[:,3]=unw(view[:,3]); view[:,1]=unw(view[:,1])
t0=aos[0,0]
gm=np.sqrt((dm[:,1:]**2).sum(1))
# 표본 간격 이상
for name,a in (("aos",aos),("ros",ros),("dm",dm),("view",view)):
    d=np.diff(a[:,0]); print(name,"간격 ms 중앙",round(float(np.median(d)),1),"p99",round(float(np.percentile(d,99)),1),"최대",round(float(d.max()),1),">150ms 횟수",int((d>150).sum()))
# aos 표본 간 최대 점프(자이로 대비)
da=np.abs(np.diff(aos[:,1])); dt=np.diff(aos[:,0])/1000
g_at=np.interp(aos[1:,0],dm[:,0],gm)
exc=da-(g_at*dt*1.5+1.0)
idx=np.argsort(exc)[-8:][::-1]
print("\naos 표본 간 변화가 자이로로 설명 안 되는 상위:")
for i in idx: print(f"  t={(aos[i+1,0]-t0)/1000:7.2f}s Δaos={da[i]:6.1f}° dt={dt[i]*1000:5.0f}ms gyro={g_at[i]:6.1f}°/s pitch={aos[i+1,2]:5.1f}")
sel=[int(x) for x in sys.argv[2:]]
for k in sel:
    m=marks[k-1]; print(f"\n== mark {k} (t={(m-t0)/1000:.1f}s) — 100ms 간격, 0 = 누른 순간 | gyro°/s | aos | ros(맞춤) | diff | view | aosPitch")
    ts=np.arange(m-3500,m+600,100.0)
    A=np.interp(ts,aos[:,0],aos[:,1]); R=np.interp(ts,ros[:,0],ros[:,1]); G=np.interp(ts,dm[:,0],gm); V=np.interp(ts,view[:,0],view[:,3]); P=np.interp(ts,aos[:,0],aos[:,2])
    off=A[0]-R[0]; V=V-(np.round((V[0]-A[0])/360)*360)
    for j,t in enumerate(ts):
        print(f"{(t-m)/1000:+5.1f} {G[j]:6.1f} {A[j]:8.1f} {R[j]+off:8.1f} {A[j]-R[j]-off:+6.1f} {V[j]:8.1f} {P[j]:6.1f}")
