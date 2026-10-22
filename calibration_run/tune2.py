import json, sys, numpy as np, collections
from types import SimpleNamespace
sys.path.insert(0,"src")
from light_map.input.gestures import is_finger_extended
rows=[json.loads(l) for l in open("calibration_run/gesture_record.jsonl")]
exp={"PUNO":"CLOSED_FIST","ROCK":"ROCK","PISTOLA":"GUN","PAZ":"VICTORY","PALMA":"OPEN_PALM","SENALAR":"POINTING"}
# trim first 25% of every segment (transition)
seg=collections.defaultdict(list)
for r in rows:
    if r["gesture"] in exp: seg[r["gesture"]].append(r)
data=[]
for g,lst in seg.items():
    for r in lst[int(len(lst)*0.25):]:
        if r["hands"]: data.append((g,r["hands"][0]))
fing={"Index":(5,6,8),"Middle":(9,10,12),"Ring":(13,14,16),"Pinky":(17,18,20)}
A=16/9
def pt(lm,i): return np.array([lm[i][0]*A,lm[i][1],lm[i][2]*A])
def ang(lm,m,p,t):
    v1=pt(lm,m)-pt(lm,p); v2=pt(lm,t)-pt(lm,p)
    return np.degrees(np.arccos(np.clip(v1@v2/(np.linalg.norm(v1)*np.linalg.norm(v2)+1e-9),-1,1)))
def classify(s):
    T,I,M,R,P=s["Thumb"],s["Index"],s["Middle"],s["Ring"],s["Pinky"]
    if all(s.values()): return "OPEN_PALM"
    if not any(s.values()): return "CLOSED_FIST"
    if T and I and not M and not R and not P: return "GUN"
    if I and not M and not R and not P: return "POINTING"
    if I and M and not R and not P: return "VICTORY"
    if I and P and not M and not R: return "ROCK"
    if T and P and not I and not M and not R: return "SHAKA"
    return "UNKNOWN"
def run(thr_by, thumb_mode):
    res=collections.defaultdict(collections.Counter)
    for g,h in data:
        lm=h["landmarks"]; pts=[SimpleNamespace(x=p[0],y=p[1]) for p in lm]
        s={f:ang(lm,*idx)>thr_by[f] for f,idx in fing.items()}
        s["Thumb"]=is_finger_extended(pts,"Thumb",h["label"]) if thumb_mode=="old" else None
        # thumb: free in most gestures -> treat as in old logic
        res[g][classify(s)]+=1
    return res
for thr in (120,130,140,150,160):
    res=run({f:thr for f in fing},"old")
    accs={g:round(100*res[g][exp[g]]/sum(res[g].values())) for g in exp}
    print(thr, accs, "mean", round(np.mean(list(accs.values()))))
# old method on same trimmed data
old=collections.defaultdict(collections.Counter)
from light_map.input.gestures import detect_gesture
for g,h in data:
    pts=[SimpleNamespace(x=p[0],y=p[1]) for p in h["landmarks"]]
    old[g][detect_gesture(pts,h["label"]).name]+=1
accs={g:round(100*old[g][exp[g]]/sum(old[g].values())) for g in exp}
print("old", accs, "mean", round(np.mean(list(accs.values()))))

print("--- confusion with angle thr 140 + old thumb")
res=run({f:140 for f in fing},"old")
for g in exp: print(g, dict(res[g].most_common(4)))
# thumb alternatives
def run2(rule):
    res=collections.defaultdict(collections.Counter)
    for g,h in data:
        lm=h["landmarks"]
        s={f:ang(lm,*idx)>140 for f,idx in fing.items()}
        palm=np.linalg.norm(pt(lm,5)-pt(lm,17))
        a_ip=ang(lm,2,3,4); d_p=np.linalg.norm(pt(lm,4)-pt(lm,17))/palm
        s["Thumb"]=rule(a_ip,d_p)
        res[g][classify(s)]+=1
    return res
for name,rule in {"ip>=160":lambda a,d:a>=160,"ip>=160 or d>=1.85":lambda a,d:a>=160 or d>=1.85,"ip>=158 or d>=1.8":lambda a,d:a>=158 or d>=1.8,"ip>=162 or d>=1.9":lambda a,d:a>=162 or d>=1.9}.items():
    r=run2(rule); accs={g:round(100*r[g][exp[g]]/sum(r[g].values())) for g in exp}
    print(name,accs,"mean",round(np.mean(list(accs.values()))))
