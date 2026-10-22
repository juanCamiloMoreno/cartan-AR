import json, numpy as np, collections
rows=[json.loads(l) for l in open("calibration_run/gesture_record.jsonl")]
A=16/9
def pt(lm,i): return np.array([lm[i][0]*A,lm[i][1],lm[i][2]*A])
def ang(lm,a,b,c):
    v1=pt(lm,a)-pt(lm,b); v2=pt(lm,c)-pt(lm,b)
    return np.degrees(np.arccos(np.clip(v1@v2/(np.linalg.norm(v1)*np.linalg.norm(v2)+1e-9),-1,1)))
seg=collections.defaultdict(list)
for r in rows: seg[r["gesture"]].append(r)
out={}
for g in ("PUNO","PISTOLA","SENALAR","PAZ","ROCK","PALMA"):
    lst=seg[g]; lst=lst[int(len(lst)*0.25):]
    F=collections.defaultdict(list)
    for r in lst:
        if not r["hands"]: continue
        lm=r["hands"][0]["landmarks"]
        palm=np.linalg.norm(pt(lm,5)-pt(lm,17))
        F["ang_ip"].append(ang(lm,2,3,4))
        F["ang_mcp"].append(ang(lm,1,2,3))
        F["tip_idxmcp/palm"].append(np.linalg.norm(pt(lm,4)-pt(lm,5))/palm)
        F["tip_idxpip/palm"].append(np.linalg.norm(pt(lm,4)-pt(lm,6))/palm)
        F["tip_pinkymcp/palm"].append(np.linalg.norm(pt(lm,4)-pt(lm,17))/palm)
    out[g]={k:np.percentile(v,[10,50,90]).round(2).tolist() for k,v in F.items()}
for k in ("ang_ip","ang_mcp","tip_idxmcp/palm","tip_idxpip/palm","tip_pinkymcp/palm"):
    print("==",k,"(p10,p50,p90)")
    for g in out: print(f"  {g:8s}",out[g][k])
