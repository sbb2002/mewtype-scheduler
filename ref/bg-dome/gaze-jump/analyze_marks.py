import sys,csv,math
import numpy as np
f=sys.argv[1]
D={}
for r in csv.reader(open(f,encoding="utf-8")):
    if len(r)<2: continue
    D.setdefault(r[1],[]).append(r)
def arr(k,cols):
    rows=[r for r in D.get(k,[]) if all(len(r)>c and r[c]!="" for c in cols)]
    return np.array([[float(r[0])]+[float(r[c]) for c in cols] for r in rows])
aos=arr("aos",[2,3]); ros=arr("ros",[2,3]); dm=arr("dm",[2,3,4,5,6,7]); view=arr("view",[2,3,4,5]); doa=arr("doa",[2,3,4]); do=arr("do",[2,3,4])
marks=[float(r[0]) for r in D.get("mark",[])]
unw=lambda a: np.degrees(np.unwrap(np.radians(a)))
for a in (aos,ros,view): a[:,1]=unw(a[:,1])
view[:,3]=unw(view[:,3])
t0=aos[0,0]; print("dur s",(aos[-1,0]-t0)/1000, "rates Hz", {k:round(len(D[k])/((aos[-1,0]-t0)/1000),1) for k in D if k not in("info","mark")})
print("src:", set(r[6] for r in D["view"] if len(r)>6))
# 공통 격자 20ms
T=np.arange(max(aos[0,0],ros[0,0],dm[0,0])+50, min(aos[-1,0],ros[-1,0],dm[-1,0]), 20.0)
ip=lambda a,c: np.interp(T,a[:,0],a[:,c])
A=ip(aos,1); R=ip(ros,1); Ap=ip(aos,2); Rp=ip(ros,2); V=ip(view,3)
gm=np.interp(T,dm[:,0],np.sqrt(dm[:,1]**2+dm[:,2]**2+dm[:,3]**2))
diff=A-R   # 절대 − 상대: 자력계 보정이 움직인 양
np.save("T.npy",T)
print("\n자이로 회전속도 크기 중앙값/정지 비율(<3°/s):",round(float(np.median(gm)),2), round(float((gm<3).mean()),2))
print("diff(aos-ros) 전체 범위°:",round(diff.min(),1),round(diff.max(),1))
def win(t,a,b): return (T>=t+a)&(T<=t+b)
print("\nmark별 [-5s,+1s]: dA=aos 방위 변화, dR=ros 방위 변화, dDiff=보정 변화, 자이로 최대°/s, 정지중(자이로<5) aos 이동 최대")
for i,m in enumerate(marks):
    w=win(m,-5000,1000)
    if w.sum()<10: print(i+1,"범위 밖"); continue
    a,r,d,g=A[w],R[w],diff[w],gm[w]
    still=g<5
    # 정지 구간 안에서 1초 창 aos 최대 이동
    best=0;bt=0
    tt=T[w]
    for j in range(0,len(tt)-50,5):
        if still[j:j+50].all():
            mv=a[j:j+50].max()-a[j:j+50].min()
            if mv>best: best=mv;bt=(tt[j]-m)/1000
    print(f"{i+1:2d} t={((m-t0)/1000):6.1f}s dA={a.max()-a.min():6.1f} dR={r.max()-r.min():6.1f} dDiff={d.max()-d.min():6.1f} gyroMax={g.max():6.1f} still%={still.mean():.2f} 정지중1초aos이동={best:5.1f}°(@{bt:+.1f}s) viewΔ={V[w].max()-V[w].min():6.1f}")
# 전체에서 정지 중인데 diff 가 빨리 변한 사건 찾기
dd=np.abs(diff[50:]-diff[:-50])   # 1초간 변화
stillrun=np.array([ (gm[i:i+50]<5).all() for i in range(len(T)-50)])
ev=np.where((dd>3)&stillrun)[0]
print("\n정지(1초 내내 자이로<5°/s) 중 diff 1초 변화>3° 표본 수:",len(ev),"/",stillrun.sum())
# 사건 묶기
groups=[]
for i in ev:
    if groups and T[i]-groups[-1][1]<1500: groups[-1][1]=T[i]; groups[-1][2]=max(groups[-1][2],dd[i])
    else: groups.append([T[i],T[i],dd[i]])
for g in groups:
    near=min(marks,key=lambda m:abs(m-g[0])) if marks else None
    print(f"  사건 t={(g[0]-t0)/1000:6.1f}~{(g[1]-t0)/1000+1:6.1f}s 최대 1초변화={g[2]:5.1f}°  가장 가까운 mark까지 {((near-g[0])/1000 if near else float('nan')):+.1f}s")
