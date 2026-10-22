import json, collections, sys
from types import SimpleNamespace
sys.path.insert(0, "src")
from light_map.input.gestures import detect_gesture, is_finger_extended
rows=[json.loads(l) for l in open("calibration_run/gesture_record.jsonl")]
exp={"PUNO":"CLOSED_FIST","ROCK":"ROCK","PISTOLA":"GUN","PAZ":"VICTORY","PALMA":"OPEN_PALM","SENALAR":"POINTING"}
F=("Thumb","Index","Middle","Ring","Pinky")
stats=collections.defaultdict(lambda: collections.Counter())
fing=collections.defaultdict(lambda: collections.Counter())
frames=collections.Counter(); detected=collections.Counter()
for r in rows:
    g=r["gesture"]; frames[g]+=1
    if not r["hands"]: continue
    detected[g]+=1
    h=r["hands"][0]
    pts=[SimpleNamespace(x=p[0],y=p[1]) for p in h["landmarks"]]
    stats[g][detect_gesture(pts,h["label"]).name]+=1
    for f in F:
        if is_finger_extended(pts,f,h["label"]): fing[g][f]+=1
for g in exp:
    n=detected[g]
    print(f"{g:8s} frames={frames[g]:3d} manos={n:3d}  esperado={exp[g]:12s} app dice: {dict(stats[g].most_common(4))}")
    print("         dedos extendidos (%):", {f: round(100*fing[g][f]/max(n,1)) for f in F})
