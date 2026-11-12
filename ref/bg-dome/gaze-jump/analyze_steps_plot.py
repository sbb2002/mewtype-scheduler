import sys,csv,numpy as np
f=sys.argv[1]; out=sys.argv[2]; D={}
for r in csv.reader(open(f,encoding="utf-8")):
    if len(r)>=2: D.setdefault(r[1],[]).append(r)
def arr(k,cols):
    rows=[r for r in D.get(k,[]) if all(len(r)>c and r[c]!="" for c in cols)]
    return np.array([[float(r[0])]+[float(r[c]) for c in cols] for r in rows])
aos=arr("aos",[2,3]); ros=arr("ros",[2,3]); dm=arr("dm",[2,3,4]); view=arr("view",[2,3,4,5])
marks=np.array([float(r[0]) for r in D.get("mark",[])])
unw=lambda a: np.degrees(np.unwrap(np.radians(a)))
aos[:,1]=unw(aos[:,1]); ros[:,1]=unw(ros[:,1]); view[:,3]=unw(view[:,3])
gm=np.sqrt((dm[:,1:]**2).sum(1)); t0=aos[0,0]
# aos 시각에 ros 보간 → diff. 40초 공백(화면 꺼짐/탭 전환) 앞뒤는 제외
R=np.interp(aos[:,0],ros[:,0],ros[:,1]); diff=aos[:,1]-R; t=aos[:,0]
dt=np.diff(t); step=np.diff(diff); ok=dt<100
G=np.interp(t[1:],dm[:,0],gm); P=aos[1:,2]
big=np.where(ok&(np.abs(step)>2.0))[0]
print("표본 사이 diff(aos−ros) 계단 >2°:",len(big),"회 / 기록",round((t[-1]-t0)/1000),"s (공백 40s 포함)")
print("그중 |pitch|<60°:",int((np.abs(P[big])<60).sum()), " 자이로<10°/s(정지):",int((G[big]<10).sum()))
print(" t(s)  계단°  자이로°/s  pitch  가장 가까운 mark까지(s, +면 계단 뒤에 누름)")
for i in big:
    d=(marks-t[i+1])/1000; j=np.argmin(np.abs(d)) if len(marks) else None
    print(f"{(t[i+1]-t0)/1000:6.1f} {step[i]:+6.1f} {G[i]:8.1f} {P[i]:6.1f}   {d[j]:+6.1f}" if j is not None else "")
# mark 마다 앞 4초 안 계단
print("\nmark별 직전 4초 안의 계단(>2°):")
for k,m in enumerate(marks):
    s=[(round((t[i+1]-m)/1000,2),round(float(step[i]),1),round(float(G[i]),1)) for i in big if -4000<=t[i+1]-m<=300]
    print(k+1,s)
# 계단 사이 느린 흐름: 정지 중 diff 기울기
try:
    import matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt
    seg=t>(marks[0]-12000) if len(marks) else np.ones_like(t,bool)
    fig,ax=plt.subplots(3,1,figsize=(13,8),sharex=True)
    x=(t-t0)/1000
    ax[0].plot(x[seg],aos[seg,1],label="aos (absolute, with magnetometer)",lw=1); ax[0].plot(x[seg],R[seg]+(aos[seg,1][0]-R[seg][0]),label="ros (relative, gyro+accel)",lw=1)
    vs=(view[:,0]>t[seg][0]); V=view[vs,3]; V=V-np.round((V[0]-aos[seg,1][0])/360)*360
    ax[0].plot((view[vs,0]-t0)/1000,V,label="rendered view yaw",lw=.8,alpha=.7); ax[0].set_ylabel("yaw (deg, unwrapped)"); ax[0].legend(loc="upper left",fontsize=8)
    ax[1].plot(x[seg],diff[seg]-diff[seg][0],color="C3",lw=1); ax[1].set_ylabel("aos - ros (deg)\n= magnetometer correction")
    ds=(dm[:,0]>t[seg][0]); ax[2].plot((dm[ds,0]-t0)/1000,gm[ds],color="gray",lw=.7); ax[2].set_ylabel("gyro |rate| (deg/s)"); ax[2].set_xlabel("time (s)")
    for a in ax:
        for m in marks: a.axvline((m-t0)/1000,color="r",ls="--",lw=.8)
    ax[0].set_title("Gaze jump log - red dashed = operator pressed the label button")
    fig.tight_layout(); fig.savefig(out,dpi=110); print("plot",out)
except Exception as e: print("plot fail",e)
