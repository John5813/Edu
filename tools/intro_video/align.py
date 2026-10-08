import json,re,subprocess,math,sys
sc=json.load(open('scenes.json',encoding='utf-8'))
# text units with boundary types
text=""; tb=[]   # (char_pos, kind, scene_end_id)
for s in sc:
    t=s['text']
    for m in re.finditer(r'[.!?:,](?=\s|$)',t):
        k='S' if m.group() in '.!?' else ('C' if m.group()==':' else 'c')
        if m.end()==len(t): k='E'
        tb.append((len(text)+m.end(),k,s['id']))
    text+=t+" "
def ln(a,b): return len(re.sub(r"[^\w]","",text[a:b]))
r=subprocess.run(["ffmpeg","-hide_banner","-i","audio/narration.mp3","-af","silencedetect=noise=-38dB:d=0.18","-f","null","-"],capture_output=True,text=True).stderr
st=[float(x) for x in re.findall(r"silence_start: ([\d.]+)",r)]
en=[float(x) for x in re.findall(r"silence_end: ([\d.]+)",r)]
TOTAL=float(subprocess.run(["ffprobe","-v","error","-show_entries","format=duration","-of","csv=p=0","audio/narration.mp3"],capture_output=True,text=True).stdout)
sil=list(zip(st,en))
if sil and sil[0][0]<0.05: speech0=sil[0][1]; sil=sil[1:]
else: speech0=0
if sil and sil[-1][1]>=TOTAL-0.05: speechN=sil[-1][0]; sil=sil[:-1]
else: speechN=TOTAL
# audio boundaries: (start_sil,end_sil)
AB=[(speech0,speech0)]+sil+[(speechN,speechN)]
TB=[(0,'B',None)]+tb
speech_total=sum(b[0]-a[1] for a,b in zip(AB,AB[1:]))
chars=ln(0,len(text))
rate=speech_total/chars
print(f"speech {speech_total:.1f}s chars {chars} rate {1/rate:.1f} ch/s, silences {len(sil)}, text boundaries {len(tb)}",file=sys.stderr)
nA,nT=len(AB),len(TB)
INF=1e18
best=[[INF]*nT for _ in range(nA)]; bp=[[None]*nT for _ in range(nA)]
best[0][0]=0
skipT={'E':6.0,'S':3.0,'C':1.0,'c':0.15}
def skipA(i):
    d=AB[i][1]-AB[i][0]; return 0.3+8*max(0,d-0.25)
for i in range(1,nA):
    for j in range(1,nT):
        if i==nA-1 and j!=nT-1: continue
        for pi in range(max(0,i-4),i):
            sa=sum(skipA(x) for x in range(pi+1,i))
            for pj in range(max(0,j-6),j):
                if best[pi][pj]>=INF: continue
                st_=sum(skipT[TB[x][1]] for x in range(pj+1,j))
                dur=AB[i][0]-AB[pi][1]
                c=ln(TB[pj][0],TB[j][0])
                if c==0 or dur<=0: continue
                cost=best[pi][pj]+ (math.log(dur/(c*rate))/0.25)**2 + sa+st_
                if cost<best[i][j]: best[i][j]=cost; bp[i][j]=(pi,pj)
i,j=nA-1,nT-1; pairs=[]
while (i,j)!=(0,0):
    pairs.append((i,j)); i,j=bp[i][j]
pairs.reverse()
prev=(0,0); cuts={}
for i,j in pairs:
    dur=AB[i][0]-AB[prev[0]][1]; c=ln(TB[prev[1]][0],TB[j][0])
    print(f"{AB[prev[0]][1]:7.2f}-{AB[i][0]:7.2f} {dur:5.2f}s exp {c*rate:5.2f}  {TB[j][1]} | {text[TB[prev[1]][0]:TB[j][0]].strip()[:70]}")
    if TB[j][1]=='E': cuts[TB[j][2]]=(AB[prev[0]][1] if False else None, i)
    prev=(i,j)
# scene spans
out=[];start=AB[0][1]
for i,j in pairs:
    if TB[j][1]=='E':
        out.append((TB[j][2],start,AB[i][0])); start=AB[i][1]
json.dump(out,open('audio/spans.json','w'))
for o in out: print(o)

# --- split per scene + subtitle cues (gap-to-gap pieces, relative to scene start) ---
LEAD,TAIL=0.06,0.15
import os
os.makedirs('audio',exist_ok=True)
cues={}; prev=(0,0); k=0
starts={sid:a for sid,a,b in out}
for i,j in pairs:
    sid=TB[j][2] if TB[j][1]=='E' else None
    a,b=AB[prev[0]][1],AB[i][0]
    t=text[TB[prev[1]][0]:TB[j][0]].strip()
    cur=out[k][0]
    s0=max(0,starts[cur]-LEAD)
    cues.setdefault(cur,[]).append({"text":t,"start":round(a-s0,3),"end":round(b-s0,3),"brk":TB[j][1]})
    if TB[j][1]=='E': k+=1
    prev=(i,j)
for sid,a,b in out:
    s0=max(0,a-LEAD); e=min(TOTAL,b+TAIL) if sid!=out[-1][0] else TOTAL
    subprocess.run(["ffmpeg","-y","-v","error","-ss",f"{s0:.3f}","-to",f"{e:.3f}","-i","audio/narration.mp3","-af","afade=t=out:st=%.3f:d=0.05"%(e-s0-0.05),"-ar","48000","-ac","1",f"audio/{sid}.wav"],check=True)
json.dump(cues,open('audio/cues.json','w',encoding='utf-8'),ensure_ascii=False,indent=1)
print("split ok")
