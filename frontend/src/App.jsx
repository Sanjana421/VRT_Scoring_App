import { useState, useRef, useEffect, useCallback } from "react";

/* --- Design tokens --------------------------------------------------- */
const T = {
  bg:"#080E17",bg1:"#0D1520",bg2:"#111C2C",bg3:"#162033",bg4:"#1C2A40",
  border:"rgba(255,255,255,0.07)",border2:"rgba(255,255,255,0.12)",
  text1:"#EAE8E1",text2:"#9B9890",text3:"#565450",
  blue:"#2B7FE0",blueD:"rgba(43,127,224,0.15)",blueB:"rgba(43,127,224,0.3)",
  green:"#1A9E72",greenD:"rgba(26,158,114,0.15)",greenB:"rgba(26,158,114,0.3)",
  amber:"#C07A0A",amberD:"rgba(192,122,10,0.15)",amberB:"rgba(192,122,10,0.3)",
  red:"#C03535",redD:"rgba(192,53,53,0.15)",redB:"rgba(192,53,53,0.3)",
  purple:"#6B5FD4",purpleD:"rgba(107,95,212,0.15)",
};

/* --- Role display labels (internal role id → shown label) ------------- */
const ROLE_LABEL = { scorer: "Research Assistant", professor: "PI/Admin", r3: "3rd Reviewer" };
const roleLabel = (r) => ROLE_LABEL[r] || r;

/* --- API helper ------------------------------------------------------- */
const API = "";  // same origin; Vite proxy routes /api → FastAPI in dev

async function apiFetch(path, opts = {}) {
  const res = await fetch(API + path, {
    headers: { "Content-Type": "application/json" },
    cache: "no-store",   // always hit the server so dashboards show live data
    ...opts,
  });
  if (!res.ok) {
    let msg = `HTTP ${res.status}`;
    try {
      const j = await res.json();
      const d = j.detail ?? j.message ?? msg;
      // FastAPI validation errors return an array of objects - flatten to text
      // so the UI never shows "[object Object]".
      if (Array.isArray(d)) {
        msg = d.map(e => e?.msg || (typeof e === "string" ? e : JSON.stringify(e))).join("; ");
      } else if (typeof d === "object") {
        msg = d.msg || JSON.stringify(d);
      } else {
        msg = String(d);
      }
    } catch {}
    throw new Error(msg);
  }
  return res.json();
}

/* --- Re-usable components --------------------------------------------- */
function Tag({color="blue",children,small}){
  const m={blue:{bg:T.blueD,b:T.blueB,t:"#6EB3FF"},green:{bg:T.greenD,b:T.greenB,t:"#4ECFA0"},
    amber:{bg:T.amberD,b:T.amberB,t:"#F5B84A"},red:{bg:T.redD,b:T.redB,t:"#F08080"},
    purple:{bg:T.purpleD,b:"rgba(107,95,212,0.3)",t:"#B0A8F5"},
    gray:{bg:"rgba(255,255,255,0.05)",b:T.border2,t:T.text2}};
  const c=m[color]||m.blue;
  return <span style={{display:"inline-flex",alignItems:"center",background:c.bg,
    border:`0.5px solid ${c.b}`,color:c.t,borderRadius:6,
    fontSize:small?10:11,fontWeight:500,padding:small?"2px 7px":"3px 9px",
    letterSpacing:"0.2px",whiteSpace:"nowrap"}}>{children}</span>;
}

function Btn({onClick,children,variant="primary",disabled,style:s}){
  const st={primary:{background:T.blue,color:"#fff",border:"none"},
    ghost:{background:"transparent",color:T.text2,border:`0.5px solid ${T.border2}`},
    danger:{background:T.redD,color:"#F08080",border:`0.5px solid ${T.redB}`},
    success:{background:T.greenD,color:"#4ECFA0",border:`0.5px solid ${T.greenB}`},
    amber:{background:T.amberD,color:"#F5B84A",border:`0.5px solid ${T.amberB}`}};
  return <button onClick={onClick} disabled={disabled} style={{...st[variant],borderRadius:8,
    padding:"9px 18px",fontSize:13,fontWeight:500,cursor:disabled?"not-allowed":"pointer",
    opacity:disabled?0.45:1,fontFamily:"inherit",transition:"opacity 0.15s",...s}}>{children}</button>;
}

function Card({children,style:s}){
  return <div style={{background:T.bg2,border:`0.5px solid ${T.border}`,borderRadius:12,...s}}>{children}</div>;
}

function StatCard({value,label,color=T.text1,sub}){
  return <div style={{background:T.bg3,border:`0.5px solid ${T.border}`,borderRadius:10,padding:"14px 16px"}}>
    <div style={{fontSize:24,fontWeight:600,color,lineHeight:1,marginBottom:4,fontVariantNumeric:"tabular-nums"}}>{value}</div>
    <div style={{fontSize:11,color:T.text3,textTransform:"uppercase",letterSpacing:"0.6px"}}>{label}</div>
    {sub&&<div style={{fontSize:11,color:T.text2,marginTop:3}}>{sub}</div>}
  </div>;
}

function SectionHeader({title,sub,right}){
  return <div style={{display:"flex",alignItems:"flex-start",justifyContent:"space-between",marginBottom:20}}>
    <div>
      <div style={{fontSize:16,fontWeight:600,color:T.text1,letterSpacing:"-0.2px"}}>{title}</div>
      {sub&&<div style={{fontSize:12,color:T.text3,marginTop:3}}>{sub}</div>}
    </div>
    {right}
  </div>;
}

function NavItem({icon,label,active,onClick,badge}){
  return <div onClick={onClick} style={{display:"flex",alignItems:"center",gap:10,
    padding:"9px 16px",cursor:"pointer",borderRadius:8,
    background:active?T.bg4:"transparent",color:active?T.text1:T.text2,
    fontSize:13,fontWeight:active?500:400,transition:"all 0.12s",margin:"1px 8px",
    borderLeft:active?`2px solid ${T.blue}`:"2px solid transparent"}}>
    <span style={{fontSize:15,width:18,textAlign:"center"}}>{icon}</span>
    <span style={{flex:1}}>{label}</span>
    {badge!=null&&<Tag color="red" small>{badge}</Tag>}
  </div>;
}

function ErrBanner({msg,onClose}){
  if(!msg) return null;
  return <div style={{background:T.redD,border:`0.5px solid ${T.redB}`,borderRadius:8,
    padding:"10px 14px",marginBottom:14,display:"flex",alignItems:"center",gap:10}}>
    <span style={{fontSize:12,color:"#F08080",flex:1}}>{msg}</span>
    <button onClick={onClose} style={{background:"none",border:"none",color:"#F08080",
      cursor:"pointer",fontSize:14,padding:0}}>✕</button>
  </div>;
}

/* --- Main App --------------------------------------------------------- */
export default function App(){
  const [screen, setScreen]       = useState("login");
  const [session, setSession]     = useState(null);
  const [run, setRun]             = useState(null);
  const [trialIdx, setTrialIdx]   = useState(0);
  const [trialData, setTrialData] = useState(null);
  const [lastSaved, setLastSaved] = useState(null);
  const [status, setStatus]       = useState(null);
  const [flagged, setFlagged]     = useState([]);
  const [err, setErr]             = useState("");
  const [r3Trial, setR3Trial]     = useState(null);
  const [analytics, setAnalytics] = useState(null);
  const [trialsScored, setTrialsScored] = useState(0);   // this session
  const [listsScored, setListsScored]   = useState(0);   // runs completed this session
  const [sessionStart, setSessionStart] = useState(null); // Date.now() at login
  const savedIdxRef = useRef(new Set()); // 0-based indices scored by THIS session on the current run

  const showSidebar = session && screen !== "login";

  const clearErr = () => setErr("");

  const handleLogin = useCallback(async (name, role, passcode="") => {
    try {
      const r = await apiFetch("/api/session/start", {
        method: "POST",
        body: JSON.stringify({ reviewer_name: name, role, version: "v5", passcode }),
      });
      setSession({ reviewer_name: r.reviewer_name, initials: r.initials, role });
      savedIdxRef.current = new Set();
      setRun(null); setTrialIdx(0); setTrialData(null); setLastSaved(null);
      setTrialsScored(0); setListsScored(0); setSessionStart(Date.now());
      setScreen("dashboard");
      // load status in background
      apiFetch("/api/status").then(setStatus).catch(()=>{});
      return true;
    } catch(e) { setErr(e.message); return false; }
  }, []);

  const handleSignOut = useCallback(async () => {
    try { await apiFetch("/api/session", { method: "DELETE" }); } catch {}
    setSession(null); setRun(null); setTrialIdx(0);
    setTrialData(null); setLastSaved(null); setScreen("login");
  }, []);

  const handleAssignRun = useCallback(async () => {
    clearErr();
    try {
      const r = await apiFetch("/api/session/assign-run", { method: "POST" });
      if (!r.ok) { setErr(r.message || "No runs available."); return false; }
      setRun(r);
      setTrialIdx(0);
      setTrialData(null);
      return true;
    } catch(e) { setErr(e.message); return false; }
  }, []);

  const handleLoadTrial = useCallback(async (idx) => {
    clearErr();
    try {
      const t = await apiFetch(`/api/trial/${idx}`);
      if (!t.ok) { setErr(t.message); return; }
      setTrialIdx(idx);
      setTrialData(t);
    } catch(e) { setErr(e.message); }
  }, []);

  const handleSaveTrial = useCallback(async (trialNum, vrt, respScore, recheck, cutoff) => {
    clearErr();
    try {
      const r = await apiFetch("/api/trial/save", {
        method: "POST",
        body: JSON.stringify({ trial_num: trialNum, vrt, resp_score: respScore, recheck, cutoff }),
      });
      if (!r.ok) { setErr(r.message); return false; }
      setLastSaved({ trialNum, vrt, respScore, recheck, cutoff });
      return true;
    } catch(e) { setErr(e.message); return false; }
  }, []);

  const handleCompleteRun = useCallback(async () => {
    clearErr();
    try {
      const r = await apiFetch("/api/run/complete", { method: "POST" });
      if (!r.ok) { setErr(r.message); return false; }
      setRun(null); setTrialIdx(0); setTrialData(null);
      return true;
    } catch(e) { setErr(e.message); return false; }
  }, []);

  const handleLoadFlagged = useCallback(async () => {
    clearErr();
    try {
      const r = await apiFetch("/api/professor/flagged");
      setFlagged(r.flagged || []);
    } catch(e) { setErr(e.message); }
  }, []);

  const handleLoadAnalytics = useCallback(async () => {
    clearErr();
    try { setAnalytics(await apiFetch("/api/analytics")); }
    catch(e) { setErr(e.message); }
  }, []);

  const handleApproveR3 = useCallback(async (trials) => {
    clearErr();
    try {
      const r = await apiFetch("/api/professor/approve-r3", {
        method: "POST",
        body: JSON.stringify({ trials }),
      });
      return r;
    } catch(e) { setErr(e.message); return null; }
  }, []);

  const handleLoadR3Trial = useCallback(async () => {
    clearErr();
    try {
      const r = await apiFetch("/api/r3/next-trial");
      if (!r.ok) { setErr(r.message || "No R3 trials available."); return; }
      setR3Trial(r);
    } catch(e) { setErr(e.message); }
  }, []);

  const handleSaveR3 = useCallback(async (vrt, respScore, recheck, cutoff) => {
    clearErr();
    try {
      const r = await apiFetch("/api/r3/save", {
        method: "POST",
        body: JSON.stringify({ vrt, resp_score: respScore, recheck, cutoff }),
      });
      if (!r.ok) { setErr(r.message); return false; }
      setR3Trial(null);
      return true;
    } catch(e) { setErr(e.message); return false; }
  }, []);

  // Start scoring in one step: reuse the current run if one is in progress,
  // otherwise claim the next run and open trial 1. Replaces the old Queue page.
  const startScoring = useCallback(async () => {
    if (run) { setScreen("scorer"); return; }
    clearErr();
    const r = await apiFetch("/api/session/assign-run", { method: "POST" })
      .catch(e => { setErr(e.message); return null; });
    if (!r || !r.ok) { if (r) setErr(r.message || "No runs available."); return; }
    savedIdxRef.current = new Set();
    setRun(r);
    setTrialData(null);
    // Resume: jump to the first unscored trial instead of trial 1.
    await handleLoadTrial(r.start_index || 0);
    setScreen("scorer");
  }, [run, handleLoadTrial]);

  const roleNav = session?.role === "professor"
    ? [
        {id:"dashboard",icon:"⊞",label:"Dashboard"},
        {id:"recheck",  icon:"⚑",label:"3rd coder review"},
        {id:"analytics",icon:"◈",label:"Analytics"},
      ]
    : session?.role === "r3"
    ? [
        {id:"dashboard",icon:"⊞",label:"Dashboard"},
        {id:"r3scorer", icon:"∿",label:"R3 scoring"},
      ]
    : [
        {id:"dashboard",icon:"⊞",label:"Dashboard"},
        {id:"scorer",   icon:"∿",label:"Waveform scorer"},
      ];

  return (
    <div style={{display:"flex",flexDirection:"column",height:"100vh",overflow:"hidden",background:T.bg,
      fontFamily:"'DM Mono','DM Sans','Segoe UI',monospace",color:T.text1}}>
      {/* TOP BAR */}
      <div style={{height:52,display:"flex",alignItems:"center",justifyContent:"space-between",
        borderBottom:`0.5px solid ${T.border}`,background:T.bg1,padding:"0 24px",flexShrink:0}}>
        <div style={{display:"flex",alignItems:"center",gap:12}}>
          <div style={{width:30,height:30,borderRadius:8,background:T.blue,display:"flex",
            alignItems:"center",justifyContent:"center",fontSize:13,fontWeight:700,color:"#fff"}}>VRT</div>
          <span style={{fontSize:14,fontWeight:600,letterSpacing:"-0.3px"}}>VRT Scoring</span>
        </div>
        {session && (
          <div style={{display:"flex",alignItems:"center",gap:12}}>
            <div style={{textAlign:"right"}}>
              <div style={{fontSize:12,color:T.text1,fontWeight:500}}>{session.reviewer_name}</div>
              <div style={{fontSize:11,color:T.text3}}>Initials: {session.initials} · {roleLabel(session.role)}</div>
            </div>
            <div style={{width:32,height:32,borderRadius:"50%",background:T.blueD,
              border:`1px solid ${T.blueB}`,display:"flex",alignItems:"center",justifyContent:"center",
              fontSize:12,fontWeight:600,color:"#6EB3FF"}}>{session.initials}</div>
            <Btn variant="ghost" style={{padding:"5px 12px",fontSize:12}} onClick={handleSignOut}>Sign out</Btn>
          </div>
        )}
      </div>

      <div style={{display:"flex",flex:1,overflow:"hidden"}}>
        {/* SIDEBAR */}
        {showSidebar && (
          <div style={{width:180,flexShrink:0,borderRight:`0.5px solid ${T.border}`,
            background:T.bg1,padding:"16px 0",display:"flex",flexDirection:"column",overflowY:"auto"}}>
            {roleNav.map(n=>(
              <NavItem key={n.id} icon={n.icon} label={n.label}
                active={screen===n.id}
                onClick={()=> n.id==="scorer" ? startScoring() : setScreen(n.id)}/>
            ))}
            <div style={{flex:1}}/>
          </div>
        )}

        {/* MAIN CONTENT */}
        <div style={{flex:1,minHeight:0,overflowY:"auto",padding:showSidebar?"16px 20px":0}}>
          {err && <div style={{padding:showSidebar?"0 0 12px":"16px 24px 0"}}>
            <ErrBanner msg={err} onClose={clearErr}/>
          </div>}
          {screen==="login"     && <LoginScreen onLogin={handleLogin}/>}
          {screen==="dashboard" && <DashboardScreen session={session} status={status} setScreen={setScreen}
            onStart={startScoring}
            onRefreshStatus={()=>apiFetch("/api/status").then(setStatus).catch(()=>{})}
            trialsScored={trialsScored} listsScored={listsScored} sessionStart={sessionStart}/>}
          {screen==="scorer"    && <ScorerScreen session={session} run={run} trialIdx={trialIdx}
            trialData={trialData} totalTrials={run?.total_trials||25}
            onLoadTrial={handleLoadTrial}
            onSaveTrial={async(trialNum,vrt,respScore,recheck,cutoff)=>{
              const ok=await handleSaveTrial(trialNum,vrt,respScore,recheck,cutoff);
              if(!ok) return;
              setTrialsScored(n=>n+1);
              savedIdxRef.current.add(trialIdx);
              const total=run?.total_trials||25;
              // Trials done before this session (resumed) + trials done now.
              const scored=new Set((run?.scored_trials||[]).map(tn=>tn-1));
              savedIdxRef.current.forEach(i=>scored.add(i));
              // Advance to the first still-unscored trial anywhere in the run.
              let next=-1;
              for(let i=0;i<total;i++){ if(!scored.has(i)){ next=i; break; } }
              if(next===-1){
                // Every trial in this pass is now scored - complete the run.
                const done=await handleCompleteRun();
                if(done){ setListsScored(n=>n+1); apiFetch("/api/status").then(setStatus).catch(()=>{}); setScreen("runDone"); }
              } else {
                await handleLoadTrial(next);
              }
            }}/>}
          {screen==="runDone" && <RunDoneScreen totalTrials={run?.total_trials||25}
            trialsScored={trialsScored}
            onScoreMore={startScoring}
            onDone={()=>setScreen("dashboard")}/>}
          {screen==="recheck"   && <RecheckScreen session={session} flagged={flagged}
            onLoad={handleLoadFlagged} onApproveR3={handleApproveR3} setScreen={setScreen}/>}
          {screen==="r3scorer"  && <R3ScorerScreen r3Trial={r3Trial}
            onLoad={handleLoadR3Trial} onSave={handleSaveR3}/>}
          {screen==="analytics" && <AnalyticsScreen data={analytics} onLoad={handleLoadAnalytics}/>}
        </div>
      </div>
    </div>
  );
}

/* -- S-01 LOGIN ------------------------------------------------------- */
function LoginScreen({onLogin}){
  const[name,setName]=useState("");
  const[role,setRole]=useState("scorer");
  const[passcode,setPasscode]=useState("");
  const[loading,setLoading]=useState(false);
  const mkInit=n=>{const p=n.trim().split(/\s+/);if(!n.trim())return"";
    return p.length===1?p[0].replace(/[^A-Za-z]/g,"").slice(0,3).toUpperCase():(p[0][0]+(p.find((_,i)=>i>0&&p[i].match(/[A-Za-z]/))?.[0]||"")).toUpperCase();};
  const auto=mkInit(name);
  const inp={width:"100%",background:T.bg3,border:`0.5px solid ${T.border2}`,boxSizing:"border-box",
    borderRadius:8,padding:"10px 14px",fontSize:14,color:T.text1,fontFamily:"inherit",outline:"none"};
  const handleSubmit=async()=>{
    if(!name.trim())return;
    if(role==="professor"&&!passcode.trim())return;
    setLoading(true);
    await onLogin(name.trim(),role,passcode);
    setLoading(false);
  };
  return(
    <div style={{minHeight:"100vh",display:"flex",alignItems:"center",justifyContent:"center",background:T.bg}}>
      <div style={{width:420}}>
        <div style={{textAlign:"center",marginBottom:36}}>
          <div style={{width:60,height:60,borderRadius:15,background:T.blue,
            display:"flex",alignItems:"center",justifyContent:"center",
            fontSize:22,fontWeight:800,color:"#fff",margin:"0 auto 16px"}}>VRT</div>
          <div style={{fontSize:24,fontWeight:700,letterSpacing:"-0.5px",marginBottom:4}}>VRT Scoring</div>
          <div style={{fontSize:13,color:T.text3}}>CARES Lab · Children's Auditory Research for Educational Success</div>
        </div>
        <Card style={{padding:28}}>
          <div style={{marginBottom:18}}>
            <label style={{fontSize:12,color:T.text2,display:"block",marginBottom:6}}>Reviewer full name</label>
            <input value={name} onChange={e=>setName(e.target.value)}
              onKeyDown={e=>e.key==="Enter"&&handleSubmit()}
              style={inp} placeholder="e.g. Sarah Gustafson" autoFocus/>
          </div>
          <div style={{marginBottom:18}}>
            <label style={{fontSize:12,color:T.text2,display:"block",marginBottom:6}}>Initials (auto-generated)</label>
            <div style={{...inp,color:"#6EB3FF",fontWeight:700,letterSpacing:"2px",
              border:`0.5px solid ${T.blueB}`,cursor:"default"}}>{auto||"-"}</div>
            <div style={{fontSize:11,color:T.text3,marginTop:5}}>Your initials will be recorded in the scoring log</div>
          </div>
          <div style={{marginBottom:26}}>
            <label style={{fontSize:12,color:T.text2,display:"block",marginBottom:6}}>Role</label>
            <select value={role} onChange={e=>setRole(e.target.value)} style={{...inp,cursor:"pointer"}}>
              <option value="scorer">Research Assistant</option>
              <option value="professor">PI/Admin</option>
              <option value="r3">3rd Reviewer</option>
            </select>
          </div>
          {role==="professor"&&(
            <div style={{marginBottom:26}}>
              <label style={{fontSize:12,color:T.text2,display:"block",marginBottom:6}}>PI/Admin passcode</label>
              <input type="password" value={passcode} onChange={e=>setPasscode(e.target.value)}
                onKeyDown={e=>e.key==="Enter"&&handleSubmit()}
                style={inp} placeholder="Required for PI/Admin access" autoComplete="off"/>
            </div>
          )}
          {(() => { const disabled = !name.trim() || loading || (role==="professor" && !passcode.trim());
          return <button onClick={handleSubmit} disabled={disabled}
            style={{width:"100%",background:T.blue,border:"none",borderRadius:9,padding:13,
              fontSize:14,fontWeight:600,color:"#fff",cursor:disabled?"not-allowed":"pointer",fontFamily:"inherit",
              opacity:disabled?0.5:1}}>
            {loading?"Starting...":"Start scoring session →"}
          </button>; })()}
        </Card>
      </div>
    </div>
  );
}

/* -- S-02 DASHBOARD --------------------------------------------------- */
function DashboardScreen({session,status,setScreen,onStart,onRefreshStatus,trialsScored,listsScored,sessionStart}){
  const [elapsed,setElapsed]=useState(0);
  useEffect(()=>{
    onRefreshStatus();
    if(!sessionStart)return;
    const tick=()=>setElapsed(Math.floor((Date.now()-sessionStart)/1000));
    tick();
    const id=setInterval(tick,30000);
    return()=>clearInterval(id);
  },[]);
  const role=session?.role;
  const fmtTime=(ts)=>{if(!ts)return"-";const d=new Date(ts);return d.toLocaleTimeString([],{hour:"2-digit",minute:"2-digit"});};
  const fmtElapsed=(s)=>{const m=Math.floor(s/60);const h=Math.floor(m/60);return h>0?`${h}h ${m%60}m`:`${m} min`;};

  if(role==="scorer")return <div>
    <SectionHeader title={`Welcome, ${session?.reviewer_name?.split(" ")[0]||"Scorer"}`}
      right={<Btn onClick={onStart}>Start scoring →</Btn>}/>
    <div style={{display:"grid",gridTemplateColumns:"repeat(3,1fr)",gap:12}}>
      <StatCard value={listsScored} label="Lists scored this session" color="#4ECFA0"/>
      <StatCard value={trialsScored} label="Words scored this session" color="#6EB3FF"/>
      <StatCard value={elapsed>0?fmtElapsed(elapsed):"-"} label="Time spent scoring"/>
    </div>
  </div>;

  // 3rd reviewer: minimal dashboard - only their own R3 queue, no R1/R2 totals.
  if(role==="r3")return <div>
    <SectionHeader title={`Welcome, ${session?.reviewer_name?.split(" ")[0]||"Reviewer"}`}
      right={<Btn onClick={()=>setScreen("r3scorer")}>Start R3 scoring →</Btn>}/>
    <div style={{display:"grid",gridTemplateColumns:"repeat(2,1fr)",gap:12}}>
      <StatCard value={status?.r3_pending??"-"} label="R3 trials waiting" color="#B0A8F5"/>
      <StatCard value={elapsed>0?fmtElapsed(elapsed):"-"} label="Time spent scoring"/>
    </div>
  </div>;

  return <div>
    <SectionHeader title={`Welcome, ${session?.reviewer_name?.split(" ")[0]||"Reviewer"}`}
      right={
        role==="professor"?<Btn onClick={()=>setScreen("recheck")}>Review flagged →</Btn>:
        <Btn onClick={()=>setScreen("r3scorer")}>Start R3 scoring →</Btn>
      }/>
    <div style={{display:"grid",gridTemplateColumns:"repeat(4,1fr)",gap:12,marginBottom:16}}>
      <StatCard value={status?.total_runs??"-"}    label="Total runs"/>
      <StatCard value={status?.r1_complete??"-"}   label="R1 complete" color="#6EB3FF"/>
      <StatCard value={status?.both_complete??"-"} label="Both complete" color="#4ECFA0"/>
      <StatCard value={status?.r3_pending??"-"}    label="R3 pending" color="#F5B84A"/>
    </div>
    {role==="professor"&&status?.both_complete>0&&(
      <div style={{background:T.amberD,border:`0.5px solid ${T.amberB}`,borderRadius:10,
        padding:"14px 18px",display:"flex",alignItems:"center",gap:14}}>
        <div style={{fontSize:18}}>⚑</div>
        <div style={{flex:1}}>
          <div style={{fontSize:13,fontWeight:600,color:"#F5B84A"}}>{status.both_complete} runs fully scored - check for flagged trials</div>
          <div style={{fontSize:12,color:T.text2,marginTop:2}}>Runs where both R1 and R2 are complete may have recheck/cutoff flags waiting for your review.</div>
        </div>
        <Btn variant="amber" onClick={()=>setScreen("recheck")} style={{flexShrink:0}}>Review →</Btn>
      </div>
    )}
  </div>;
}

/* -- WAVEFORM CANVAS --------------------------------------------------- */
// startPct / endPct are WINDOW fractions (0-1 of the whole waveform window),
// NOT view fractions. The canvas converts them to on-screen x using the current
// zoom view [viewStart, viewEnd] so markers stay anchored to the same audio
// position at every zoom level (and playback/VRT, which also use window
// fractions, stay in sync).
function WaveCanvas({samples, startPct, endPct, onStartPct, onEndPct,
                     viewStart, viewEnd, windowStart, windowEnd, playheadPct, onViewChange}){
  const ref = useRef(null);
  const drag = useRef(null); // 'start' | 'end' | {mode:'pan', x, vs, ve} | null

  const totalSamples = samples?.length || 2000;
  const vs = viewStart ?? 0;
  const ve = viewEnd ?? totalSamples;

  // window-fraction -> view proportion (0-1 across the visible canvas)
  const fracToViewPct = (frac) => (frac * totalSamples - vs) / ((ve - vs) || 1);
  // click position on canvas (0-1) -> window fraction
  const viewPctToFrac = (p) => (vs + p * (ve - vs)) / (totalSamples || 1);
  const getViewPct = (e) => {
    const r = ref.current?.getBoundingClientRect();
    if (!r) return 0;
    return Math.max(0, Math.min(1, (e.clientX - r.left) / r.width));
  };

  // Keep a zoom view within [0, total] and above a minimum width (max zoom).
  const clampView = (start, end) => {
    const minW = 8, maxW = totalSamples;
    let w = end - start;
    if (w >= maxW) return [0, maxW];
    if (w < minW) { const c = (start + end) / 2; start = c - minW / 2; end = c + minW / 2; }
    if (start < 0) { end -= start; start = 0; }
    if (end > totalSamples) { start -= (end - totalSamples); end = totalSamples; }
    if (start < 0) start = 0;
    return [Math.round(start), Math.round(end)];
  };

  // Smooth wheel zoom, centered on the cursor. Native listener so we can
  // preventDefault (React's onWheel is passive and cannot).
  useEffect(() => {
    const c = ref.current;
    if (!c || !onViewChange) return;
    const onWheel = (e) => {
      e.preventDefault();
      const r = c.getBoundingClientRect();
      const p = Math.max(0, Math.min(1, (e.clientX - r.left) / r.width));
      const cursorSample = vs + p * (ve - vs);
      const factor = e.deltaY < 0 ? 0.82 : 1 / 0.82;   // scroll up = zoom in
      const newW = (ve - vs) * factor;
      onViewChange(...clampView(cursorSample - p * newW, cursorSample + (1 - p) * newW));
    };
    c.addEventListener("wheel", onWheel, { passive: false });
    return () => c.removeEventListener("wheel", onWheel);
  }, [vs, ve, totalSamples, onViewChange]);

  const GRAB = 0.03; // how close (in view proportion) a click must be to grab a marker

  const handleDown = (e) => {
    const p = getViewPct(e);
    const sVP = Math.max(0, Math.min(1, fracToViewPct(startPct)));
    const eVP = Math.max(0, Math.min(1, fracToViewPct(endPct)));
    const dS = Math.abs(p - sVP), dE = Math.abs(p - eVP);
    if (Math.min(dS, dE) <= GRAB) {
      drag.current = dS <= dE ? 'start' : 'end';
      handleMove(e); // fine-adjust to the click within the grab zone
    } else {
      drag.current = { mode: 'pan', x: e.clientX, vs, ve };
    }
  };

  const handleMove = (e) => {
    const d = drag.current;
    if (!d) return;
    if (d === 'start') {
      onStartPct(Math.max(0, Math.min(viewPctToFrac(getViewPct(e)), endPct - 0.003)));
    } else if (d === 'end') {
      onEndPct(Math.max(startPct + 0.003, Math.min(1, viewPctToFrac(getViewPct(e)))));
    } else if (d.mode === 'pan' && onViewChange) {
      const r = ref.current?.getBoundingClientRect();
      if (!r) return;
      const shift = -((e.clientX - d.x) / r.width) * (d.ve - d.vs);
      onViewChange(...clampView(d.vs + shift, d.ve + shift));
    }
  };

  useEffect(()=>{
    const c = ref.current;
    if (!c) return;
    const ctx = c.getContext("2d");
    const W = c.width, H = c.height;
    ctx.clearRect(0, 0, W, H);

    // Background
    ctx.fillStyle = T.bg3;
    ctx.fillRect(0, 0, W, H);

    const viewSamples = samples ? samples.slice(vs, ve) : [];

    // Marker on-screen positions (window fraction -> canvas x), clamped to view
    const clampX = (x) => Math.max(0, Math.min(W, x));
    const sx = clampX(fracToViewPct(startPct) * W);
    const ex = clampX(fracToViewPct(endPct) * W);
    ctx.fillStyle = "rgba(43,127,224,0.07)";
    ctx.fillRect(sx, 0, ex - sx, H);

    if (viewSamples.length > 1) {
      const drawHalf = (sign) => {
        ctx.beginPath();
        for (let i = 0; i < W; i++) {
          const si = Math.floor((i / W) * viewSamples.length);
          const amp = viewSamples[si] ?? 0;
          const y = H / 2 + sign * amp * (H * 0.44);
          i === 0 ? ctx.moveTo(i, y) : ctx.lineTo(i, y);
        }
        ctx.strokeStyle = "rgba(43,127,224,0.6)";
        ctx.lineWidth = 1.2;
        ctx.stroke();
      };
      drawHalf(1);
      drawHalf(-1);
    } else {
      ctx.fillStyle = T.text3;
      ctx.font = "12px monospace";
      ctx.textAlign = "center";
      ctx.fillText("Loading waveform...", W/2, H/2);
    }

    // Center line
    ctx.beginPath(); ctx.moveTo(0, H/2); ctx.lineTo(W, H/2);
    ctx.strokeStyle = "rgba(255,255,255,0.05)"; ctx.lineWidth = 0.5; ctx.stroke();

    // Time ticks
    const winDur = (windowEnd??4) - (windowStart??0);
    const viewTimeFrac = ve > vs && samples?.length
      ? [(vs/samples.length)*winDur + (windowStart??0),
         (ve/samples.length)*winDur + (windowStart??0)]
      : [windowStart??0, windowEnd??4];
    const tStep = winDur <= 1 ? 0.25 : winDur <= 2 ? 0.5 : 1;
    ctx.fillStyle = "rgba(255,255,255,0.25)";
    ctx.font = "10px monospace";
    ctx.textAlign = "left";
    for (let t = Math.ceil(viewTimeFrac[0]/tStep)*tStep; t <= viewTimeFrac[1]+0.001; t += tStep) {
      const px = ((t - viewTimeFrac[0]) / (viewTimeFrac[1] - viewTimeFrac[0])) * W;
      ctx.fillText(t.toFixed(2)+"s", px + 3, H - 4);
    }

    // Playhead (orange - moves during playback)
    if (playheadPct !== null && playheadPct !== undefined) {
      const totalSamples = samples?.length || 2000;
      const phFrac = (playheadPct * totalSamples - (viewStart??0)) / ((viewEnd??totalSamples) - (viewStart??0));
      if (phFrac >= 0 && phFrac <= 1) {
        const px = phFrac * W;
        ctx.beginPath(); ctx.moveTo(px, 0); ctx.lineTo(px, H);
        ctx.strokeStyle = "#FF8C00"; ctx.lineWidth = 2; ctx.stroke();
      }
    }

    // -- End marker (amber, right) - draw first so start overlaps if they meet
    ctx.beginPath(); ctx.moveTo(ex, 0); ctx.lineTo(ex, H);
    ctx.strokeStyle = "#C07A0A"; ctx.lineWidth = 2; ctx.stroke();
    // Handle: triangle pointing left at top
    ctx.fillStyle = "#C07A0A";
    ctx.beginPath(); ctx.moveTo(ex, 0); ctx.lineTo(ex - 12, 8); ctx.lineTo(ex, 16); ctx.fill();
    // End time label (window fraction -> absolute time)
    const endTime = (windowStart??0) + endPct * winDur;
    const elabel = endTime.toFixed(3) + "s";
    const elx = ex > W - 60 ? ex - 58 : ex + 4;
    ctx.fillStyle = "rgba(192,122,10,0.9)";
    ctx.beginPath(); ctx.roundRect(elx, 20, 56, 16, 3); ctx.fill();
    ctx.fillStyle = "#fff"; ctx.font = "bold 10px monospace";
    ctx.textAlign = "left"; ctx.fillText(elabel, elx + 4, 32);

    // -- Start marker (green, left) - VRT
    ctx.beginPath(); ctx.moveTo(sx, 0); ctx.lineTo(sx, H);
    ctx.strokeStyle = "#1A9E72"; ctx.lineWidth = 2; ctx.stroke();
    // Handle: triangle pointing right at top
    ctx.fillStyle = "#1A9E72";
    ctx.beginPath(); ctx.moveTo(sx, 0); ctx.lineTo(sx + 12, 8); ctx.lineTo(sx, 16); ctx.fill();
    // Start time label (VRT) (window fraction -> absolute time)
    const startTime2 = (windowStart??0) + startPct * winDur;
    const slabel = startTime2.toFixed(3) + "s";
    const slx = sx > W - 60 ? sx - 58 : sx + 4;
    ctx.fillStyle = "rgba(26,158,114,0.9)";
    ctx.beginPath(); ctx.roundRect(slx, 38, 56, 16, 3); ctx.fill();
    ctx.fillStyle = "#fff"; ctx.font = "bold 10px monospace";
    ctx.textAlign = "left"; ctx.fillText(slabel, slx + 4, 50);

  }, [samples, startPct, endPct, viewStart, viewEnd, windowStart, windowEnd, playheadPct]);

  return <canvas ref={ref} width={1200} height={240}
    style={{width:"100%",height:"clamp(180px, 38vh, 460px)",cursor:"crosshair",display:"block"}}
    onMouseDown={handleDown}
    onMouseMove={handleMove}
    onMouseUp={()=>{drag.current=null;}}
    onMouseLeave={()=>{drag.current=null;}}/>;
}

/* -- S-04 WAVEFORM SCORER ---------------------------------------------- */
const SCORE_MAP = {correct:"Correct",incorrect:"Incorrect",noresp:"No Response",unclear:"Not Scored"};
const SCORES = [
  {id:"correct",  label:"Correct",        icon:"✓",c:T.green, bg:T.greenD, b:T.greenB, tc:"#4ECFA0"},
  {id:"incorrect",label:"Incorrect",      icon:"✗",c:T.red,   bg:T.redD,   b:T.redB,   tc:"#F08080"},
  {id:"noresp",   label:"No response",    icon:"-",c:T.amber, bg:T.amberD, b:T.amberB, tc:"#F5B84A"},
  {id:"unclear",  label:"Unsure",         icon:"~",c:T.purple,bg:T.purpleD,b:"rgba(107,95,212,0.3)",tc:"#B0A8F5"},
];

function ScorerScreen({session,run,trialIdx,trialData,totalTrials,onLoadTrial,onSaveTrial}){
  const [startPct, setStartPct]     = useState(0);   // green start marker (VRT)
  const [endPct, setEndPct]         = useState(1);   // amber end marker
  const [score, setScore]           = useState(null);
  const [recheck, setRecheck]       = useState(false);
  const [cutoff, setCutoff]         = useState(false);
  const [revealed, setRevealed]     = useState(false);
  const [view, setView]             = useState(null); // [startSample, endSample] or null = full
  const [saving, setSaving]         = useState(false);
  const [playing, setPlaying]         = useState(false);
  const [playheadPct, setPlayheadPct] = useState(null);
  const [audioReady, setAudioReady]   = useState(false);
  const audioCtx      = useRef(null);
  const audioSrc      = useRef(null);
  const audioBuffer   = useRef(null);
  const startTime     = useRef(null);
  const playOffsetRef = useRef(0);    // offset (seconds) into buffer where playback started
  const playDurRef    = useRef(null); // duration to play (null = to end)
  const animFrameRef  = useRef(null);

  // Trials already scored by a previous person on this pass (cross-person
  // handoff). Blinded: we never see their scores, we just skip past them, and
  // the server also rejects any attempt to overwrite them.
  const lockedSet = new Set(run?.scored_trials || []);
  const alreadyDone = (run?.scored_trials || []).length;

  // Keep our claim alive while actively scoring so the handoff logic doesn't
  // treat us as "left" and reassign this run to someone else.
  useEffect(()=>{
    const id = setInterval(()=>{
      apiFetch("/api/session/heartbeat", { method: "POST" }).catch(()=>{});
    }, 30000);
    return ()=>clearInterval(id);
  }, []);

  // Load trial on mount / when trialIdx changes
  useEffect(()=>{
    if (!run) return;
    if (!trialData || trialData.trial_num !== (trialIdx + 1)) {
      onLoadTrial(trialIdx);
    }
  }, [trialIdx, run]);

  // Safety net: if we ever land on an already-scored trial, skip forward.
  useEffect(()=>{
    if (!trialData) return;
    if (lockedSet.has(trialData.trial_num) && trialIdx + 1 < totalTrials) {
      onLoadTrial(trialIdx + 1);
    }
  }, [trialData]);

  // Reset UI state when new trialData arrives
  useEffect(()=>{
    if (!trialData) return;
    setStartPct(0);    // start marker defaults to beginning
    setEndPct(1);      // end marker defaults to end of window
    setScore(null);
    setRecheck(false);
    setCutoff(false);
    setRevealed(false);
    setView(null);
    setPlayheadPct(null);
    setAudioReady(false);
    playOffsetRef.current = 0;
    playDurRef.current = null;
    audioBuffer.current = null;
  }, [trialData]);

  // Preload audio
  useEffect(()=>{
    if (!trialData?.wav_exists || !run) return;
    const {obs_name,visit_num,snr,dist_cond,run_num} = run;
    const tn = trialData.trial_num;
    const url = `/api/audio/${obs_name}/${visit_num}/${snr}/${dist_cond}/${run_num}/${tn}`;
    if (!audioCtx.current) audioCtx.current = new (window.AudioContext||window.webkitAudioContext)();
    fetch(url)
      .then(r => { if (!r.ok) throw new Error(`HTTP ${r.status} loading audio`); return r.arrayBuffer(); })
      .then(buf => audioCtx.current.decodeAudioData(buf))
      .then(decoded => { audioBuffer.current = decoded; setAudioReady(true); })
      .catch(err => { console.error('[VRT] Audio load failed:', err, 'URL:', url); });
  }, [trialData, run]);

  const playAudio = useCallback(()=>{
    if (!audioBuffer.current || !audioCtx.current) return;
    if (audioSrc.current) { try { audioSrc.current.stop(); } catch {} }

    // Play only the region between start and end markers
    const winStart  = trialData?.window_start ?? 0;
    const winEnd    = trialData?.window_end   ?? 4;
    const windowDur = winEnd - winStart;
    // Buffer-absolute offset (window may not start at t=0 in the file)
    const bufOffset = winStart + startPct * windowDur;
    const dur       = (endPct - startPct) * windowDur;
    // Window-relative offset for animation tracking
    playOffsetRef.current = startPct * windowDur;
    playDurRef.current    = dur;

    const src = audioCtx.current.createBufferSource();
    src.buffer = audioBuffer.current;
    src.connect(audioCtx.current.destination);
    audioCtx.current.resume().then(() => {
      const startAt = audioCtx.current.currentTime + 0.02; // tiny schedule buffer
      src.start(startAt, bufOffset);
      src.stop(startAt + dur);  // explicit stop time - more reliable than duration param
      src.onended = () => {
        setPlaying(false);
        setPlayheadPct(null);
        if (animFrameRef.current) cancelAnimationFrame(animFrameRef.current);
      };
      audioSrc.current = src;
      startTime.current = startAt;
      setPlaying(true);
    });
  }, [startPct, endPct, trialData]);

  // Animate playhead while playing
  useEffect(()=>{
    if (!playing) {
      if (animFrameRef.current) cancelAnimationFrame(animFrameRef.current);
      return;
    }
    const windowDur = (trialData?.window_end ?? 4) - (trialData?.window_start ?? 0);
    const tick = () => {
      if (!audioCtx.current || !startTime.current) return;
      // elapsed since src.start() was scheduled (startTime is the scheduled start, not now)
      const elapsed = Math.max(0, audioCtx.current.currentTime - startTime.current);
      const posInWindow = (playOffsetRef.current + elapsed) / windowDur;
      // Cap at end marker so playhead doesn't overshoot
      const maxPos = playDurRef.current != null
        ? (playOffsetRef.current + playDurRef.current) / windowDur
        : 1;
      setPlayheadPct(Math.min(maxPos, Math.max(0, posInWindow)));
      animFrameRef.current = requestAnimationFrame(tick);
    };
    animFrameRef.current = requestAnimationFrame(tick);
    return () => { if (animFrameRef.current) cancelAnimationFrame(animFrameRef.current); };
  }, [playing, trialData]);

  const stopAudio = useCallback(()=>{
    if (audioSrc.current) { try { audioSrc.current.stop(); } catch {} audioSrc.current=null; }
    setPlaying(false);
    setPlayheadPct(null);
    if (animFrameRef.current) cancelAnimationFrame(animFrameRef.current);
  }, []);

  // Warn before browser refresh/close - scores are saved per trial, mid-trial work would be lost
  useEffect(()=>{
    const handler = (e) => {
      e.preventDefault();
      e.returnValue = "Your current trial score has not been saved yet. Leave anyway?";
      return e.returnValue;
    };
    window.addEventListener("beforeunload", handler);
    return ()=>window.removeEventListener("beforeunload", handler);
  }, []);

  // Keyboard shortcuts: Space=play, R=reset, 1-4=score
  useEffect(()=>{
    const handler = (e) => {
      if (e.target.tagName === "INPUT" || e.target.tagName === "TEXTAREA") return;
      if (e.code === "Space") { e.preventDefault(); playing ? stopAudio() : playAudio(); }
      if (e.key.toLowerCase() === "r") { setStartPct(0); setEndPct(1); }
      // Keys match the on-screen button order (top to bottom)
      if (e.key === "1") setScore("correct");
      if (e.key === "2") setScore("incorrect");
      if (e.key === "3") setScore("noresp");
      if (e.key === "4") setScore("unclear");
    };
    window.addEventListener("keydown", handler);
    return ()=>window.removeEventListener("keydown", handler);
  }, [playing, playAudio, stopAudio]);

  // Free pan/zoom view (independent of the markers, so dragging a marker never
  // moves the waveform). null = full window.
  const samples = trialData?.waveform || [];
  const totalSamples = samples.length || 2000;
  const [viewStart, viewEnd] = view ?? [0, totalSamples];
  const zoomFactor = totalSamples / Math.max(1, (viewEnd - viewStart));

  // VRT = absolute time of start marker (voice onset)
  const winDur = (trialData?.window_end ?? 4) - (trialData?.window_start ?? 0);
  const vrt = (trialData?.window_start ?? 0) + startPct * winDur;

  const handleSave = async () => {
    if (!score) return;
    setSaving(true);
    stopAudio();
    const vrtForSave = score === "noresp" ? null : vrt;
    await onSaveTrial(
      trialData?.trial_num ?? (trialIdx+1),
      vrtForSave,
      SCORE_MAP[score],
      recheck ? 1 : 0,
      cutoff  ? 1 : 0,
    );
    setSaving(false);
  };

  const progressPct = ((trialIdx) / totalTrials * 100).toFixed(0);

  return <div>
    {/* Header - single trial-progress indicator */}
    <div style={{display:"flex",alignItems:"center",gap:10,marginBottom:14}}>
      <span style={{fontSize:16,fontWeight:600}}>Trial {trialIdx+1} of {totalTrials}</span>
      <div style={{width:140,height:4,background:T.bg4,borderRadius:2,overflow:"hidden"}}>
        <div style={{width:`${progressPct}%`,height:"100%",background:T.blue,borderRadius:2,transition:"width 0.4s"}}/>
      </div>
      {!trialData && <Tag color="gray" small>Loading...</Tag>}
      {alreadyDone>0 && <Tag color="blue" small>Resumed · {alreadyDone} already scored</Tag>}
    </div>

    <div style={{display:"grid",gridTemplateColumns:"1fr 240px",gap:14}}>
      {/* LEFT */}
      <div style={{display:"flex",flexDirection:"column",gap:12}}>
        <Card>
          <div style={{padding:"11px 16px",borderBottom:`0.5px solid ${T.border}`,
            display:"flex",alignItems:"center",justifyContent:"space-between"}}>
            <span style={{fontSize:12,color:T.text2}}>
              Response recording - <span style={{color:T.text3}}>drag <span style={{color:"#1A9E72"}}>▷ green</span> to voice onset · <span style={{color:"#C07A0A"}}>◁ amber</span> to end</span>
            </span>
            <div style={{display:"flex",alignItems:"center",gap:8}}>
              <span style={{fontSize:11,color:T.text3}}>Stim word:</span>
              <div onClick={()=>setRevealed(v=>!v)} style={{
                fontSize:13,fontWeight:600,color:"#6EB3FF",background:T.blueD,
                border:`0.5px solid ${T.blueB}`,borderRadius:6,padding:"3px 10px",
                cursor:"pointer",filter:revealed?"none":"blur(5px)",
                transition:"filter 0.25s",userSelect:"none",minWidth:40,textAlign:"center"}}
                title={revealed?"":"Click to reveal"}>
                {trialData?.stim_word||"-"}
              </div>
              {!revealed&&<span style={{fontSize:11,color:T.text3}}>click to reveal</span>}
            </div>
          </div>
          {trialData && !trialData.wav_exists &&
            <div style={{padding:"8px 16px",background:T.amberD,borderBottom:`0.5px solid ${T.amberB}`,
              fontSize:12,color:"#F5B84A"}}>
              No audio file found for this trial - it may not have been recorded. You can still score it as No response or Unsure.
            </div>}
          <WaveCanvas
            samples={samples}
            startPct={startPct}
            endPct={endPct}
            onStartPct={p => setStartPct(Math.max(0, Math.min(p, endPct - 0.01)))}
            onEndPct={p => setEndPct(Math.max(startPct + 0.01, Math.min(1, p)))}
            viewStart={viewStart}
            viewEnd={viewEnd}
            windowStart={trialData?.window_start}
            windowEnd={trialData?.window_end}
            playheadPct={playheadPct}
            onViewChange={(s,e)=>setView([s,e])}
          />
          {/* Playback controls */}
          <div style={{padding:"10px 16px",borderTop:`0.5px solid ${T.border}`,
            display:"flex",alignItems:"center",gap:8}}>
            <button onClick={playing?stopAudio:playAudio}
              disabled={!audioReady}
              style={{width:34,height:34,borderRadius:"50%",
                background:playing?T.green:audioReady?T.blue:T.bg4,
                border:"none",cursor:audioReady?"pointer":"not-allowed",
                display:"flex",alignItems:"center",justifyContent:"center",
                fontSize:13,color:"#fff",opacity:audioReady?1:0.4}}>
              {playing?"■":"▶"}
            </button>
            <Btn variant="success" style={{padding:"5px 12px",fontSize:12}}
              onClick={()=>setStartPct(p=>Math.max(0, p - 0.1/winDur))}>↩ -0.1s</Btn>
            <Btn variant="success" style={{padding:"5px 12px",fontSize:12}}
              onClick={()=>setStartPct(p=>Math.min(endPct-0.01, p + 0.1/winDur))}>+0.1s ↪</Btn>
            <Btn variant="ghost" style={{padding:"5px 12px",fontSize:12}}
              onClick={()=>{setStartPct(0);setEndPct(1);setView(null);}}>↺ Reset</Btn>
            {view && <button onClick={()=>setView(null)} style={{padding:"4px 8px",borderRadius:5,
              fontSize:11,background:T.blueD,border:`0.5px solid ${T.blueB}`,
              color:"#6EB3FF",cursor:"pointer",fontFamily:"inherit"}}>Fit</button>}
            <div style={{flex:1}}/>
            <span style={{fontSize:11,color:T.text3}}>
              scroll = zoom · drag marker to place · drag empty space to pan
              {view && <span style={{color:"#6EB3FF",marginLeft:8}}>{zoomFactor.toFixed(1)}×</span>}
            </span>
          </div>
        </Card>
        {/* VRT readout */}
        <div style={{display:"flex",alignItems:"center",gap:16,background:T.bg3,
          border:`0.5px solid ${T.border}`,borderRadius:10,padding:"14px 20px"}}>
          <div>
            <div style={{fontSize:10,color:T.text3,textTransform:"uppercase",letterSpacing:"0.6px",marginBottom:3}}>
              Voice onset (VRT)
            </div>
            <div style={{fontSize:36,fontWeight:700,color:score==="noresp"?T.text3:"#6EB3FF",
              fontVariantNumeric:"tabular-nums",letterSpacing:"-1.5px",lineHeight:1}}>
              {score==="noresp"?"NaN":<>{vrt.toFixed(3)}<span style={{fontSize:16,fontWeight:400,color:T.text3,marginLeft:4}}>sec</span></>}
            </div>
          </div>
          <div style={{flex:1}}/>
          <div style={{fontSize:11,color:T.text2,textAlign:"right"}}>
            Spacebar = play · R = reset<br/>1 = Correct · 2 = Incorrect · 3 = No response · 4 = Unsure
          </div>
        </div>
      </div>

      {/* RIGHT */}
      <div style={{display:"flex",flexDirection:"column",gap:12}}>
        <Card style={{padding:16}}>
          <div style={{fontSize:12,color:T.text2,fontWeight:500,marginBottom:10}}>Response classification</div>
          <div style={{display:"flex",flexDirection:"column",gap:7}}>
            {SCORES.map(s=>(
              <button key={s.id} onClick={()=>setScore(s.id)} style={{
                display:"flex",alignItems:"center",gap:10,padding:"11px 14px",borderRadius:8,
                background:score===s.id?s.bg:"transparent",
                border:`${score===s.id?"1.5px":"0.5px"} solid ${score===s.id?s.b:T.border2}`,
                color:score===s.id?s.tc:T.text2,cursor:"pointer",fontFamily:"inherit",
                fontSize:13,fontWeight:score===s.id?600:400,transition:"all 0.1s",textAlign:"left"}}>
                <span style={{fontSize:15,width:18,textAlign:"center",color:score===s.id?s.tc:T.text3}}>{s.icon}</span>
                {s.label}
              </button>
            ))}
          </div>
        </Card>

        <Card style={{padding:16}}>
          <div style={{fontSize:12,color:T.text2,fontWeight:500,marginBottom:10}}>Optional flags</div>
          {[
            {id:"recheck",val:recheck,set:setRecheck,label:"Recheck",sub:"Uncertain onset"},
            {id:"cutoff", val:cutoff, set:setCutoff, label:"Cutoff", sub:"Response clipped"},
          ].map(f=>(
            <div key={f.id} onClick={()=>f.set(v=>!v)} style={{
              display:"flex",alignItems:"center",gap:10,padding:"9px 12px",
              borderRadius:8,cursor:"pointer",background:f.val?T.amberD:"transparent",
              border:`0.5px solid ${f.val?T.amberB:T.border}`,marginBottom:6,transition:"all 0.1s"}}>
              <div style={{width:15,height:15,borderRadius:4,flexShrink:0,
                background:f.val?T.amber:"transparent",border:`1px solid ${f.val?T.amber:T.border2}`,
                display:"flex",alignItems:"center",justifyContent:"center"}}>
                {f.val&&<span style={{fontSize:9,color:"#fff",fontWeight:700}}>✓</span>}
              </div>
              <div>
                <div style={{fontSize:13,color:f.val?"#F5B84A":T.text2,fontWeight:f.val?500:400}}>{f.label}</div>
                <div style={{fontSize:11,color:T.text3}}>{f.sub}</div>
              </div>
            </div>
          ))}
        </Card>

        <button onClick={handleSave} disabled={!score||saving} style={{
          width:"100%",padding:13,
          background:saving?T.green:score?T.blue:T.bg4,
          border:"none",borderRadius:9,fontSize:14,fontWeight:600,
          color:score?"#fff":T.text3,cursor:score&&!saving?"pointer":"not-allowed",
          fontFamily:"inherit",transition:"background 0.25s"}}>
          {saving?"✓ Saved!":score?"Save & next trial →":"Select a score first"}
        </button>
        {!score&&<div style={{fontSize:11,color:T.amber,textAlign:"center",marginTop:-6}}>
          Select response classification before saving
        </div>}
      </div>
    </div>
  </div>;
}

/* -- S-05b RUN DONE --------------------------------------------------- */
function RunDoneScreen({totalTrials,trialsScored,onScoreMore,onDone}){
  return <div style={{maxWidth:520,margin:"60px auto 0",textAlign:"center"}}>
    <div style={{fontSize:48,marginBottom:16}}>✓</div>
    <div style={{fontSize:22,fontWeight:700,color:"#4ECFA0",marginBottom:8}}>
      Run complete - all {totalTrials} words scored
    </div>
    <div style={{fontSize:12,color:T.text3,marginBottom:32}}>
      Your initials have been written to the scoring log.
    </div>
    <div style={{display:"flex",gap:12,justifyContent:"center"}}>
      <Btn onClick={onScoreMore} style={{padding:"12px 28px",fontSize:14}}>
        Score another set →
      </Btn>
      <Btn variant="ghost" onClick={onDone} style={{padding:"12px 28px",fontSize:14}}>
        Done for now
      </Btn>
    </div>
  </div>;
}

/* -- S-06 RECHECK / CUTOFF (Professor) -------------------------------- */
function RecheckScreen({session,flagged,onLoad,onApproveR3}){
  const [selected,setSelected]=useState(new Set());
  const [msg,setMsg]=useState("");
  // Load on open and auto-refresh so newly flagged trials appear and
  // sent-to-R3 trials drop off without a manual reload.
  useEffect(()=>{ onLoad(); const id=setInterval(onLoad, 20000); return ()=>clearInterval(id); },[]);
  const sc=s=>s==="Correct"?"#4ECFA0":s==="Incorrect"?"#F08080":T.text3;
  const toggleAll=()=>setSelected(selected.size===flagged.length?new Set():new Set(flagged.map((_,i)=>i)));
  const handleApprove=async(items)=>{
    const toApprove=items||flagged.filter((_,i)=>selected.has(i));
    if(!toApprove.length) return;
    const r=await onApproveR3(toApprove);
    if(r){ setMsg(`${r.added} trial(s) sent to R3. They have been removed from this list.`);
           setSelected(new Set()); onLoad(); }
  };
  const reasonColor=r=>r.includes("mismatch")?"red":r.includes("VRT")?"amber":"purple";
  const cell=(score,vrt)=><span><span style={{color:sc(score)}}>{score||"-"}</span>
    {vrt!=null&&<span style={{color:T.text2}}> · {vrt.toFixed(3)}s</span>}</span>;
  const mismatchCount=flagged.filter(f=>(f.reasons||[]).some(r=>r.includes("mismatch"))).length;
  const vrtCount=flagged.filter(f=>(f.reasons||[]).some(r=>r.includes("VRT"))).length;
  const GRID="28px 54px 38px 150px 34px 1.1fr 0.9fr 0.9fr";
  return <div>
    <SectionHeader title="Trials needing a 3rd coder"
      sub="Trials where R1 and R2 disagree per the study rules. Select to send to R3."/>
    {msg&&<div style={{background:T.greenD,border:`0.5px solid ${T.greenB}`,borderRadius:8,
      padding:"10px 14px",marginBottom:14,fontSize:12,color:"#4ECFA0"}}>{msg}</div>}
    <div style={{display:"grid",gridTemplateColumns:"repeat(3,1fr)",gap:12,marginBottom:20}}>
      <StatCard value={flagged.length} label="Need 3rd coder" color="#F08080"/>
      <StatCard value={mismatchCount} label="Accuracy mismatch" color="#F5B84A"/>
      <StatCard value={vrtCount} label="VRT rule" color="#6EB3FF"/>
    </div>
    {flagged.length===0
      ? <Card style={{padding:24,textAlign:"center"}}>
          <div style={{fontSize:13,color:T.text2}}>No trials need a 3rd coder.</div>
          <div style={{fontSize:11,color:T.text3,marginTop:4}}>
            A trial appears here only once both R1 and R2 are complete and they disagree
            (accuracy mismatch, VRT under 0.25, VRT discrepancy over 0.25, or a recheck flag).
          </div>
          <div style={{marginTop:14}}><Btn onClick={()=>{onLoad();}} variant="ghost">Refresh →</Btn></div>
        </Card>
      : <>
          <Card>
            <div style={{padding:"10px 16px",borderBottom:`0.5px solid ${T.border}`,
              display:"grid",gridTemplateColumns:GRID,
              gap:6,fontSize:10,color:T.text3,textTransform:"uppercase",letterSpacing:"0.4px",alignItems:"center"}}>
              <input type="checkbox" onChange={toggleAll} checked={selected.size===flagged.length&&flagged.length>0}/>
              <span>Subject</span><span>Trial</span><span>Trial ID</span><span>Run</span>
              <span>Reason</span><span>R1</span><span>R2</span>
            </div>
            {flagged.map((item,i)=>(
              <div key={i} style={{display:"grid",gridTemplateColumns:GRID,
                gap:6,padding:"11px 16px",alignItems:"center",
                background:selected.has(i)?T.amberD:"transparent",
                borderBottom:i<flagged.length-1?`0.5px solid ${T.border}`:"none",fontSize:12}}>
                <input type="checkbox" checked={selected.has(i)} onChange={()=>{
                  const s=new Set(selected);s.has(i)?s.delete(i):s.add(i);setSelected(s);}}/>
                <span style={{color:"#6EB3FF",fontWeight:500}}>{item.obs_name}</span>
                <span style={{color:T.text2}}>T{item.trial_num}</span>
                <span style={{color:T.text1,fontFamily:"ui-monospace,monospace",fontSize:11}}>{item.trial_id||"-"}</span>
                <span style={{color:T.text2}}>R{item.run_num}</span>
                <div style={{display:"flex",gap:3,flexWrap:"wrap"}}>
                  {(item.reasons||[]).map((r,j)=><Tag key={j} color={reasonColor(r)} small>{r}</Tag>)}
                </div>
                {cell(item.resp_score1,item.vrt1)}
                {cell(item.resp_score2,item.vrt2)}
              </div>
            ))}
          </Card>
          <div style={{marginTop:14,display:"flex",gap:10}}>
            <Btn variant="amber" disabled={selected.size===0} onClick={()=>handleApprove()}>
              Send {selected.size} selected → R3 log
            </Btn>
            <Btn variant="ghost" onClick={()=>handleApprove(flagged)}>
              Send all → R3 log
            </Btn>
            <Btn variant="ghost" onClick={()=>{onLoad();setMsg("");}}>Refresh</Btn>
          </div>
        </>
    }
  </div>;
}

/* -- S-08 ANALYTICS (PI/Admin) ---------------------------------------- */
function AnalyticsScreen({data,onLoad}){
  const [loaded,setLoaded]=useState(false);
  useEffect(()=>{ if(!loaded){ onLoad(); setLoaded(true); } },[]);
  const pct=(n,d)=> d?((n/d*100).toFixed(1)+"%"):"-";
  const d=data;
  return <div>
    <SectionHeader title="Analytics"
      sub="R1 vs R2 agreement across all runs scored by both reviewers."
      right={<Btn variant="ghost" onClick={onLoad}>Refresh →</Btn>}/>
    {!d
      ? <Card style={{padding:24,textAlign:"center"}}>
          <div style={{fontSize:13,color:T.text2}}>Loading analytics...</div>
        </Card>
      : <>
          <div style={{display:"grid",gridTemplateColumns:"repeat(4,1fr)",gap:12,marginBottom:14}}>
            <StatCard value={pct(d.total_scored_trials,d.total_planned_trials)}
              label="Data scored (done by both R1 and R2)" color="#6EB3FF"
              sub={`${d.total_scored_trials} of ${d.total_planned_trials} trials`}/>
            <StatCard value={pct(d.accuracy_agree,d.total_scored_trials)}
              label="Accuracy agreement (R1 and R2 gave the same score)" color="#4ECFA0"
              sub={`${d.accuracy_agree} of ${d.total_scored_trials}`}/>
            <StatCard value={d.needs_third_coder} label="Need 3rd coder (R1 and R2 disagree)" color="#F5B84A"
              sub={pct(d.needs_third_coder,d.total_scored_trials)+" of scored"}/>
            <StatCard value={d.vrt_correlation==null?"-":d.vrt_correlation.toFixed(3)}
              label="VRT agreement, r (1.0 = identical timing)" color="#B0A8F5"
              sub={`${d.vrt_pairs} VRT pairs`}/>
          </div>
          <Card style={{padding:20}}>
            <div style={{fontSize:13,fontWeight:600,marginBottom:14}}>Breakdown</div>
            {[
              ["Runs scored by both reviewers", `${d.both_complete_runs} of ${d.total_runs}`],
              ["Trials scored by both reviewers", d.total_scored_trials],
              ["Accuracy - agree (same Correct / Incorrect / No response)", `${d.accuracy_agree} (${pct(d.accuracy_agree,d.total_scored_trials)})`],
              ["Accuracy - disagree (went to 3rd coder)", `${d.accuracy_disagree} (${pct(d.accuracy_disagree,d.total_scored_trials)})`],
              ["Both scored 'No response' (no VRT; counts as incorrect)", `${d.both_no_response} (${pct(d.both_no_response,d.total_scored_trials)})`],
              ["Both flagged 'Cutoff' (response clipped)", `${d.both_cutoff} (${pct(d.both_cutoff,d.total_scored_trials)})`],
              ["Trials needing a 3rd coder (any disagreement rule)", `${d.needs_third_coder} (${pct(d.needs_third_coder,d.total_scored_trials)})`],
              ["VRT pairs compared (trials both reviewers timed)", d.vrt_pairs],
              ["VRT correlation, Pearson r (1.0 = identical timing)", d.vrt_correlation==null?"-":d.vrt_correlation],
            ].map(([k,v])=>(
              <div key={k} style={{display:"flex",justifyContent:"space-between",padding:"8px 0",
                borderBottom:`0.5px solid ${T.border}`,fontSize:13}}>
                <span style={{color:T.text2}}>{k}</span>
                <span style={{color:T.text1,fontWeight:500,fontVariantNumeric:"tabular-nums"}}>{v}</span>
              </div>
            ))}
          </Card>
        </>
    }
  </div>;
}

/* -- S-R3 R3 SCORER --------------------------------------------------- */
function R3ScorerScreen({r3Trial,onLoad,onSave}){
  const [startPct,setStartPct]=useState(0);
  const [endPct,setEndPct]=useState(1);
  const [score,setScore]=useState(null);
  const [recheck,setRecheck]=useState(false);
  const [cutoff,setCutoff]=useState(false);
  const [saving,setSaving]=useState(false);
  const [loaded,setLoaded]=useState(false);
  const [revealed,setRevealed]=useState(false);
  const [view,setView]=useState(null); // [startSample,endSample] or null = full
  const [playing,setPlaying]=useState(false);
  const [playheadPct,setPlayheadPct]=useState(null);
  const [audioReady,setAudioReady]=useState(false);
  const audioCtx=useRef(null);
  const audioSrc=useRef(null);
  const audioBuffer=useRef(null);
  const startTime=useRef(null);
  const playOffsetRef=useRef(0);
  const playDurRef=useRef(null);
  const animFrameRef=useRef(null);

  useEffect(()=>{
    if(!loaded){onLoad();setLoaded(true);}
  },[]);

  useEffect(()=>{
    if(!r3Trial)return;
    // If a previous VRT exists, pre-place the start marker there
    const winD=(r3Trial.window_end??4)-(r3Trial.window_start??0);
    const prevStart=r3Trial.marker_time&&winD>0
      ?(r3Trial.marker_time-r3Trial.window_start)/winD:0;
    setStartPct(Math.max(0,Math.min(0.99,prevStart)));
    setEndPct(1);
    setScore(null);setRecheck(false);setCutoff(false);setRevealed(false);setView(null);
    setPlayheadPct(null);setAudioReady(false);
    playOffsetRef.current=0;playDurRef.current=null;
    audioBuffer.current=null;
    // preload audio
    if(r3Trial.wav_exists){
      const url=`/api/audio/${r3Trial.obs_name}/${r3Trial.visit_num}/${r3Trial.snr}/${r3Trial.dist_cond}/${r3Trial.run_num}/${r3Trial.trial_num}`;
      if(!audioCtx.current)audioCtx.current=new(window.AudioContext||window.webkitAudioContext)();
      fetch(url)
        .then(r=>{ if(!r.ok) throw new Error(`HTTP ${r.status} loading audio`); return r.arrayBuffer(); })
        .then(buf=>audioCtx.current.decodeAudioData(buf))
        .then(decoded=>{ audioBuffer.current=decoded; setAudioReady(true); })
        .catch(err=>{ console.error('[VRT] R3 audio load failed:', err, 'URL:', url); });
    }
  },[r3Trial]);

  useEffect(()=>{
    const h=(e)=>{
      if(e.target.tagName==="INPUT")return;
      if(e.code==="Space"){e.preventDefault();playing?stopAudio():playAudio();}
      if(e.key.toLowerCase()==="r"){setStartPct(0);setEndPct(1);}
      // Keys match the on-screen button order (R3 has no "Not Scored")
      if(e.key==="1")setScore("correct");
      if(e.key==="2")setScore("incorrect");
      if(e.key==="3")setScore("noresp");
    };
    window.addEventListener("keydown",h);return()=>window.removeEventListener("keydown",h);
  },[playing]);

  const playAudio=()=>{
    if(!audioBuffer.current||!audioCtx.current)return;
    if(audioSrc.current){try{audioSrc.current.stop();}catch{}}
    const winStart=r3Trial?.window_start??0;
    const winEnd=r3Trial?.window_end??4;
    const windowDur=winEnd-winStart;
    const bufOffset=winStart+startPct*windowDur;
    const dur=(endPct-startPct)*windowDur;
    playOffsetRef.current=startPct*windowDur;playDurRef.current=dur;
    const src=audioCtx.current.createBufferSource();
    src.buffer=audioBuffer.current;
    src.connect(audioCtx.current.destination);
    audioCtx.current.resume().then(()=>{
      const startAt=audioCtx.current.currentTime+0.02;
      src.start(startAt,bufOffset);
      src.stop(startAt+dur);
      src.onended=()=>{setPlaying(false);setPlayheadPct(null);if(animFrameRef.current)cancelAnimationFrame(animFrameRef.current);};
      audioSrc.current=src;startTime.current=startAt;setPlaying(true);
    });
  };
  useEffect(()=>{
    if(!playing){if(animFrameRef.current)cancelAnimationFrame(animFrameRef.current);return;}
    const windowDur=(r3Trial?.window_end??4)-(r3Trial?.window_start??0);
    const tick=()=>{
      if(!audioCtx.current||!startTime.current)return;
      const elapsed=Math.max(0,audioCtx.current.currentTime-startTime.current);
      const pos=(playOffsetRef.current+elapsed)/windowDur;
      const maxPos=playDurRef.current!=null?(playOffsetRef.current+playDurRef.current)/windowDur:1;
      setPlayheadPct(Math.min(maxPos,Math.max(0,pos)));
      animFrameRef.current=requestAnimationFrame(tick);
    };
    animFrameRef.current=requestAnimationFrame(tick);
    return()=>{if(animFrameRef.current)cancelAnimationFrame(animFrameRef.current);};
  },[playing,r3Trial]);
  const stopAudio=()=>{
    if(audioSrc.current){try{audioSrc.current.stop();}catch{}audioSrc.current=null;}
    setPlaying(false);setPlayheadPct(null);
    if(animFrameRef.current)cancelAnimationFrame(animFrameRef.current);
  };

  const samples=r3Trial?.waveform||[];
  const winDur=(r3Trial?.window_end??4)-(r3Trial?.window_start??0);
  const vrt=(r3Trial?.window_start??0)+startPct*winDur;

  const handleSave=async()=>{
    if(!score)return;
    setSaving(true);
    stopAudio();
    const ok=await onSave(score==="noresp"?null:vrt,SCORE_MAP[score],0,0); // R3 is final: no recheck/cutoff
    if(ok){setLoaded(false);}
    setSaving(false);
  };

  if(!r3Trial)return(
    <div>
      <SectionHeader title="R3 Scoring" sub="Score flagged trials approved for 3rd review."/>
      <Card style={{padding:28,textAlign:"center"}}>
        <div style={{fontSize:13,color:T.text2}}>No R3 trial loaded.</div>
        <div style={{marginTop:14}}>
          <Btn onClick={()=>{onLoad();setLoaded(true);}}>Load next R3 trial →</Btn>
        </div>
      </Card>
    </div>
  );

  return <div>
    <SectionHeader title="R3 Scoring"
      sub={`Trial ${r3Trial.trial_num} - score independently (blinded)`}/>
    {/* R3 is blinded: no R1/R2 scores or flags are shown */}
    <div style={{display:"grid",gridTemplateColumns:"1fr 240px",gap:14}}>
      <div style={{display:"flex",flexDirection:"column",gap:12}}>
        <Card>
          <div style={{padding:"11px 16px",borderBottom:`0.5px solid ${T.border}`,
            display:"flex",alignItems:"center",justifyContent:"space-between"}}>
            <span style={{fontSize:12,color:T.text2}}>Response recording</span>
            <div style={{display:"flex",alignItems:"center",gap:8}}>
              <span style={{fontSize:11,color:T.text3}}>Stim word:</span>
              <div onClick={()=>setRevealed(v=>!v)} style={{
                fontSize:13,fontWeight:600,color:"#6EB3FF",background:T.blueD,
                border:`0.5px solid ${T.blueB}`,borderRadius:6,padding:"3px 10px",
                cursor:"pointer",filter:revealed?"none":"blur(5px)",transition:"filter 0.25s",userSelect:"none"}}>
                {r3Trial.stim_word||"-"}
              </div>
              {!revealed&&<span style={{fontSize:11,color:T.text3}}>click to reveal</span>}
            </div>
          </div>
          <WaveCanvas samples={samples}
            startPct={startPct} endPct={endPct}
            onStartPct={p=>setStartPct(Math.max(0,Math.min(p,endPct-0.01)))}
            onEndPct={p=>setEndPct(Math.max(startPct+0.01,Math.min(1,p)))}
            viewStart={(view??[0,samples.length])[0]} viewEnd={(view??[0,samples.length])[1]}
            windowStart={r3Trial.window_start} windowEnd={r3Trial.window_end}
            playheadPct={playheadPct}
            onViewChange={(s,e)=>setView([s,e])}/>
          <div style={{padding:"10px 16px",borderTop:`0.5px solid ${T.border}`,display:"flex",alignItems:"center",gap:8}}>
            <button onClick={playing?stopAudio:playAudio} disabled={!audioReady}
              style={{width:34,height:34,borderRadius:"50%",
                background:playing?T.green:audioReady?T.blue:T.bg4,
                border:"none",cursor:audioReady?"pointer":"not-allowed",
                display:"flex",alignItems:"center",
                justifyContent:"center",fontSize:13,color:"#fff",opacity:audioReady?1:0.4}}>
              {playing?"■":"▶"}
            </button>
            <Btn variant="ghost" style={{padding:"5px 12px",fontSize:12}} onClick={()=>{setStartPct(0);setEndPct(1);setView(null);}}>↺ Reset</Btn>
            {view && <button onClick={()=>setView(null)} style={{padding:"4px 8px",borderRadius:5,fontSize:11,background:T.blueD,border:`0.5px solid ${T.blueB}`,color:"#6EB3FF",cursor:"pointer",fontFamily:"inherit"}}>Fit</button>}
            <div style={{flex:1}}/>
            <span style={{fontSize:11,color:T.text3}}>scroll = zoom · drag to pan</span>
          </div>
        </Card>
        <div style={{background:T.bg3,border:`0.5px solid ${T.border}`,borderRadius:10,padding:"14px 20px"}}>
          <div style={{fontSize:10,color:T.text3,textTransform:"uppercase",letterSpacing:"0.6px",marginBottom:3}}>VRT (R3)</div>
          <div style={{fontSize:32,fontWeight:700,color:"#6EB3FF",fontVariantNumeric:"tabular-nums"}}>
            {score==="noresp"?"NaN":vrt.toFixed(3)}<span style={{fontSize:14,color:T.text3,marginLeft:4}}>sec</span>
          </div>
        </div>
      </div>
      <div style={{display:"flex",flexDirection:"column",gap:12}}>
        <Card style={{padding:16}}>
          <div style={{fontSize:12,color:T.text2,fontWeight:500,marginBottom:10}}>Response classification</div>
          <div style={{display:"flex",flexDirection:"column",gap:7}}>
            {SCORES.slice(0,3).map(s=>(
              <button key={s.id} onClick={()=>setScore(s.id)} style={{
                display:"flex",alignItems:"center",gap:10,padding:"11px 14px",borderRadius:8,
                background:score===s.id?s.bg:"transparent",
                border:`${score===s.id?"1.5px":"0.5px"} solid ${score===s.id?s.b:T.border2}`,
                color:score===s.id?s.tc:T.text2,cursor:"pointer",fontFamily:"inherit",
                fontSize:13,fontWeight:score===s.id?600:400,textAlign:"left"}}>
                <span style={{fontSize:15,width:18,textAlign:"center"}}>{s.icon}</span>{s.label}
              </button>
            ))}
          </div>
        </Card>
        <button onClick={handleSave} disabled={!score||saving} style={{
          width:"100%",padding:13,background:saving?T.green:score?T.blue:T.bg4,
          border:"none",borderRadius:9,fontSize:14,fontWeight:600,
          color:score?"#fff":T.text3,cursor:score&&!saving?"pointer":"not-allowed",fontFamily:"inherit"}}>
          {saving?"✓ Saved!":score?"Save R3 score →":"Select a score first"}
        </button>
        <Btn variant="ghost" style={{width:"100%"}} onClick={()=>{onLoad();setLoaded(true);}}>
          Load next R3 trial →
        </Btn>
      </div>
    </div>
  </div>;
}

