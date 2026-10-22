import json, numpy as np, itertools
rows=[json.loads(l) for l in open("calibration_run/gesture_record.jsonl")]
W,H=1920.0,1080.0
# truth: finger -> expected extended (None = free)
truth={"PUNO":dict(I=0,M=0,R=0,P=0,T=0),"ROCK":dict(I=1,M=0,R=0,P=1,T=None),"PISTOLA":dict(T=1,I=1,M=0,R=0,P=0),
       "PAZ":dict(I=1,M=1,R=0,P=0,T=None),"PALMA":dict(I=1,M=1,R=1,P=1,T=1),"SENALAR":dict(I=1,M=0,R=0,P=0,T=None)}
# indices: (mcp,pip,dip,tip)
fing={"I":(5,6,7,8),"M":(9,10,11,12),"R":(13,14,15,16),"P":(17,18,19,20)}
def P(lm,i): return np.array([lm[i][0]*W,lm[i][1]*H,lm[i][2]*W])
def angle(a,b,c):
    v1=a-b; v2=c-b
    return np.degrees(np.arccos(np.clip(v1@v2/(np.linalg.norm(v1)*np.linalg.norm(v2)+1e-9),-1,1)))
def feats(lm):
    f={}
    wrist=P(lm,0)
    for k,(m,p,d,t) in fing.items():
        f[k+"_ang"]=angle(P(lm,m),P(lm,p),P(lm,t))          # angle at PIP (mcp-pip-tip)
        f[k+"_ang3"]=(angle(P(lm,m),P(lm,p),P(lm,d))+angle(P(lm,p),P(lm,d),P(lm,t)))/2
        f[k+"_rat"]=np.linalg.norm(P(lm,t)-wrist)/ (np.linalg.norm(P(lm,m)-wrist)+1e-9)  # tip/mcp dist ratio from wrist
    return f
data=[]
for r in rows:
    g=r["gesture"]
    if g not in truth or not r["hands"]: continue
    data.append((g,feats(r["hands"][0]["landmarks"])))
for name in ("ang","ang3","rat"):
    print("==",name)
    for k in "IMRP":
        ext=[d[k+"_"+name] for g,d in data if truth[g].get(k)==1]
        cur=[d[k+"_"+name] for g,d in data if truth[g].get(k)==0]
        print(k,"extended p10/p50:",np.percentile(ext,[10,50]).round(1),"curled p50/p90:",np.percentile(cur,[50,90]).round(1))
