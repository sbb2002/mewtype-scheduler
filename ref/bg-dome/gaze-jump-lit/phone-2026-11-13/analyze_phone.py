"""폰 기록(보정 적용판)에서 실제 화면 시선이 정지 중 혼자 움직였는지 본다. python analyze_phone.py <기록.csv> ...
혼자 움직임 = 화면에 그린 방위(view 5열) 변화 − 상대 방위(ros)를 같은 화면 감쇠에 통과시킨 값의 변화. 정지 = 상대 방위 회전 속도(0.2초 창) 8°/초 미만.
계단 = 상대 방위 변화 0.5° 미만인데 절대 방위(aos)만 2° 넘게 바뀐 이웃 표본. 시작 2초는 처음 맞추기 구간이라 따로 본다."""
import bisect, csv, math, sys

def w(x): return (x + 180) % 360 - 180

def analyze(path):
    A, R, V, FX = [], [], [], []
    for r in csv.reader(open(path, encoding='utf-8')):
        if len(r) < 3: continue
        k = r[1]
        if k == 'aos': A.append((float(r[0]), float(r[2])))
        elif k == 'ros': R.append((float(r[0]), float(r[2])))
        elif k == 'view' and r[4] != '': V.append((float(r[0]), float(r[4]), float(r[7] or 1)))
        elif k == 'fix': FX.append(r[2] == '1')
    if not A or not R or not V:
        print(f'{path}: 센서 값 부족(aos {len(A)} · ros {len(R)}) — 건너뜀\n'); return
    t0 = V[0][0]
    rt = [x[0] for x in R]
    ros_at = lambda t: R[max(0, bisect.bisect_right(rt, t) - 1)][1]
    steps = []
    for i in range(1, len(A)):
        da = w(A[i][1] - A[i-1][1]); dr = w(ros_at(A[i][0]) - ros_at(A[i-1][0]))
        if abs(da) > 2 and abs(dr) < 0.5: steps.append(((A[i][0] - t0) / 1000, da))
    dR = prevV = prevD = lastT = None; rows = []; hist = []
    for t, y, tele in V:
        r = ros_at(t)
        dt = 0.016 if lastT is None else min(0.1, (t - lastT) / 1000); lastT = t
        kk = 1 - math.exp(-dt / (0.08 + 0.36 * math.log(tele) / math.log(30)))
        dR = r if dR is None else dR + w(r - dR) * kk
        hist.append((t, r))
        while len(hist) > 2 and t - hist[0][0] > 200: hist.pop(0)
        ang = sum(abs(w(hist[i][1] - hist[i-1][1])) for i in range(1, len(hist))); span = (hist[-1][0] - hist[0][0]) / 1000
        dps = ang / span if span > 0 else 0
        if prevV is not None: rows.append(((t - t0) / 1000, dps < 8, w(y - prevV) - w(dR - prevD)))
        prevV, prevD = y, dR
    body = [x for x in rows if x[0] > 2]
    def win(rs, sec):
        best = (0, 0)
        for i, x in enumerate(rs):
            if not x[1]: continue
            s = 0
            for j in range(i, len(rs)):
                if rs[j][0] - x[0] > sec: break
                if rs[j][1]: s += rs[j][2]
            best = max(best, (abs(s), x[0]))
        return best
    print(f'== {path.split("/")[-1]}')
    print(f'길이 {(V[-1][0]-t0)/1000:.0f}초 · 보정 ON {sum(FX)}/{len(FX)} 프레임 · 정지 {sum(1 for x in body if x[1])}/{len(body)} 프레임(시작 2초 뒤)')
    print('정지 중 계단 ' + (', '.join(f'{t:.1f}s {d:+.1f}°' for t, d in steps) or '없음'))
    for ts, da in steps:
        s = m = 0
        for t, st, d in rows:
            if ts <= t <= ts + 1 and st: s += d; m = max(m, abs(s))   # 정지 프레임만(회전 중 반영분 제외)
        print(f'  계단 {ts:.1f}s {da:+.1f}° → 1초 안 정지 프레임에서 화면 혼자 움직임 최대 {m:.2f}°')
    a, t = win(body, 0.5)
    print(f'시작 2초 뒤 정지 중 0.5초 혼자 움직임 최대 {a:.2f}° ({t:.1f}s)')
    a, t = win([x for x in rows if x[0] <= 2], 0.5)
    print(f'시작 2초 안(처음 맞추기) 0.5초 혼자 움직임 최대 {a:.2f}°\n')

for p in sys.argv[1:]: analyze(p.replace(chr(92), '/'))
