import csv,sys
sys.path.insert(0, sys.argv[3])
import matplotlib; matplotlib.use('Agg'); import matplotlib.pyplot as plt
rows=[r for r in csv.DictReader(open(sys.argv[1])) if float(r['t'])>=114000]
def w(x): return (x+180)%360-180
def unwrap(xs):
    out=[xs[0]]
    for x in xs[1:]: out.append(out[-1]+w(x-out[-1]))
    return out
t=[float(r['t'])/1000 for r in rows]
R=unwrap([float(r['r']) for r in rows]); OLD=unwrap([float(r['old']) for r in rows]); NEW=unwrap([float(r['new']) for r in rows]); A=unwrap([float(r['a']) for r in rows])
import math
D=[R[0]]
for i in range(1,len(R)):
    dt=min(0.1,t[i]-t[i-1]); kk=1-math.exp(-dt/0.08); D.append(D[-1]+(R[i]-D[-1])*kk)
R=D  # 기준 = 상대 방위를 화면과 같은 감쇠에 통과시킨 것
off=OLD[0]-R[0]
marks=[128279.9,131467.3,140182.6,143726.4,147722.6,151416.4,154045.9,157366.2,160152.7,166110.6,168867.4]
fig,ax=plt.subplots(2,1,figsize=(14,7),sharex=True)
ax[0].plot(t,[w(a-(x+off)) for a,x in zip(A,R)],label='absolute sensor (aos) - damped relative',color='lightgray',lw=1)
ax[0].plot(t,[w(o-(x+off)) for o,x in zip(OLD,R)],label='NOW screen - damped relative',color='tab:red',lw=1.2)
ax[0].plot(t,[w(n-(x+off)) for n,x in zip(NEW,R)],label='NEW screen - damped relative',color='tab:blue',lw=1.2)
ax[0].set_ylabel('deg'); ax[0].legend(loc='lower left'); ax[0].grid(alpha=.3)
ax[1].plot(t,[float(r['dps']) for r in rows],color='gray',lw=.8); ax[1].axhline(8,color='k',ls=':',lw=.7)
ax[1].set_ylabel('rotation speed (deg/s)'); ax[1].set_xlabel('time (s)'); ax[1].set_ylim(0,120); ax[1].grid(alpha=.3)
for a in ax:
    for m in marks: a.axvline(m/1000,color='red',ls='--',lw=.7)
fig.suptitle('Replay g4wz (k=0.2, still<8deg/s): line moving while rotation speed is low = screen moved on its own. Red dashes = operator "jump" marks')
fig.tight_layout(); fig.savefig(sys.argv[2],dpi=100); print('ok')
