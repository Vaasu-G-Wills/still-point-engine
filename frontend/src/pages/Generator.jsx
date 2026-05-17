import { useState, useEffect, useRef } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import usePipeline from '../store/pipeline'
import { RefreshCw, Play, ChevronRight, ArrowLeft, FolderOpen, X, Move } from 'lucide-react'
import axios from 'axios'
import FolderBrowser from '../components/FolderBrowser'

const TEMPLATES = {
  still_point: [
    {key:'hook',label:'🎯 Hook'},{key:'thesis',label:'📖 Thesis'},{key:'bridge_ab',label:'🔗 Bridge A→B'},
    {key:'antithesis',label:'⚡ Antithesis'},{key:'bridge_bc',label:'🔗 Bridge B→C'},{key:'synthesis',label:'⚖️ Synthesis'},
  ],
  zerourgency: [
    {key:'hook',label:'🎯 Hook'},{key:'context',label:'📖 Context & History'},
    {key:'deep_dive',label:'⚡ Deep Dive'},{key:'takeaway',label:'⚖️ Takeaway'},
  ]
}

async function readSSE(url, opts, onEvent) {
  const res = await fetch(url, opts)
  const reader = res.body.getReader(); const dec = new TextDecoder(); let buf = ''
  while (true) {
    const {done, value} = await reader.read(); if (done) break
    buf += dec.decode(value, {stream:true})
    const parts = buf.split('\n\n'); buf = parts.pop()
    for (const p of parts) {
      const line = p.replace(/^data: /, ''); if (!line.trim()) continue
      try { onEvent(JSON.parse(line)) } catch(_) {}
    }
  }
}


/* ══ PHASE 1 ══════════════════════════════════════════════════ */
function Phase1({ projectId }) {
  const { topic, setTopic, ttsVoice, setTtsVoice, wordByWord, setWordByWord,
          channelTemplate, setChannelTemplate, setProjectId,
          addLog, clearLog, setNode, clearNodes, setOutputData, setPhase, logLines, nodes } = usePipeline()
  const [busy,        setBusy]        = useState(false)
  const [voices,      setVoices]      = useState([])
  const [llmProvider, setLlmProvider] = useState('local')
  const logRef = useRef(null)

  useEffect(() => {
    axios.get('/api/voices')
      .then(r => setVoices(r.data.voices || []))
      .catch(() => setVoices(['af_heart','af_bella','af_sarah','am_adam','am_michael','bf_emma','bf_isabella','bm_george','bm_lewis']))
  }, [])

  useEffect(() => { if (logRef.current) logRef.current.scrollTop = logRef.current.scrollHeight }, [logLines])

  const generate = async () => {
    clearLog(); clearNodes(); setBusy(true)
    addLog({type:'status', text:'Starting pipeline…'})

    let activeId = projectId
    if (!activeId) {
      addLog({type:'status', text:'📁 Creating new project record…'})
      try {
        const res = await axios.post('/api/projects', { topic, channel_template: channelTemplate })
        activeId = res.data.id
        setProjectId(activeId)
      } catch (e) {
        addLog({type:'error', text:'❌ Failed to create project record.'})
        setBusy(false); return
      }
    }

    await readSSE('/api/generate', {
      method: 'POST', headers: {'Content-Type':'application/json'},
      body: JSON.stringify({ 
        topic, 
        project_id: activeId, 
        tts_voice: ttsVoice || null, 
        word_by_word: wordByWord, 
        llm_provider: llmProvider, 
        channel_template: channelTemplate 
      }),
    }, (e) => {
      const activeNodes = TEMPLATES[channelTemplate] || []
      if (e.type === 'status') addLog({type:'status', text: e.data})
      else if (activeNodes.find(n => n.key === e.type)) { setNode(e.type, e.data); addLog({type:'content', text:`✓ ${e.type}`}) }
      else if (e.type === 'complete') { setOutputData(e.data); setPhase(2); addLog({type:'success', text:'✅ Script & audio complete!'}) }
      else if (e.type === 'error')    addLog({type:'error', text:`❌ ${e.data}`})
    })
    setBusy(false)
  }

  const hasNodes = Object.values(nodes).some(v => v.length > 0)

  return (
    <div>
      <div className="card">
        <div className="row">
          <div className="input-group" style={{flex:2}}>
            <label>Topic</label>
            <input type="text" value={topic} onChange={e => setTopic(e.target.value)}
              placeholder="e.g. The commodification of attention"
              onKeyDown={e => e.key==='Enter' && !busy && topic.trim() && generate()} />
          </div>
          <div className="input-group" style={{flex:1}}>
            <label>Channel Template</label>
            <select value={channelTemplate} onChange={e => setChannelTemplate(e.target.value)}>
              <option value="still_point">⚖️ Still Point (Dialectic)</option>
              <option value="zerourgency">📺 ZeroUrgency (Infotainment)</option>
            </select>
          </div>
        </div>
        <div className="row">
          <div className="input-group">
            <label>TTS Voice</label>
            <select value={ttsVoice} onChange={e => setTtsVoice(e.target.value)}>
              <option value="">None</option>
              {voices.map(v => <option key={v} value={v}>{v}</option>)}
            </select>
          </div>
          <div className="input-group" style={{justifyContent:'flex-end', paddingTop:24}}>
            {/* Provider toggle */}
            <div style={{display:'flex', gap:0, borderRadius:8, overflow:'hidden', border:'1px solid var(--border)', marginBottom:8}}>
              {[{v:'local', label:'⚡ Local'}, {v:'gemini', label:'✨ Gemini'}].map(({v, label}) => (
                <button key={v} onClick={() => setLlmProvider(v)}
                  style={{
                    flex:1, padding:'6px 14px', border:'none', cursor:'pointer', fontSize:12, fontWeight:600,
                    background: llmProvider === v ? 'var(--accent)' : 'transparent',
                    color:      llmProvider === v ? '#fff'          : 'var(--text-muted)',
                    transition: 'all .15s',
                  }}>{label}</button>
              ))}
            </div>
            <label style={{display:'flex', alignItems:'center', gap:8, cursor:'pointer'}}>
              <input type="checkbox" checked={wordByWord} onChange={e => setWordByWord(e.target.checked)}
                style={{width:'auto', accentColor:'var(--accent)'}} />
              Word-by-word subtitles
            </label>
          </div>
        </div>
        <button className="btn btn-primary" style={{width:'100%', justifyContent:'center'}}
          disabled={busy || !topic.trim()} onClick={generate}>
          {busy ? <><RefreshCw size={14} style={{animation:'spin 1s linear infinite'}}/> Generating…</> : <><Play size={14}/> Generate Script & Audio</>}
        </button>
      </div>

      {logLines.length > 0 && (
        <div className="sse-log" ref={logRef} style={{marginTop:14}}>
          {logLines.map((l,i) => <div key={i} className={`log-${l.type}`}>{l.text}</div>)}
        </div>
      )}

      {hasNodes && (
        <div className="node-grid">
          {(TEMPLATES[channelTemplate] || []).map(n => nodes[n.key] ? (
            <div key={n.key} className="node-card">
              <div className="node-label">{n.label}</div>
              <div className="node-text">{nodes[n.key]}</div>
            </div>
          ) : null)}
        </div>
      )}
    </div>
  )
}

/* ══ Pexels Image Picker Modal ════════════════════════════════ */
function PexelsPicker({ section, initialQuery, folderPath, onSelect, onClose }) {
  const [query,   setQuery]   = useState(initialQuery || '')
  const [results, setResults] = useState([])
  const [busy,    setBusy]    = useState(false)
  const [error,   setError]   = useState(null)

  const search = async (q) => {
    const sq = q ?? query
    if (!sq.trim()) return
    setBusy(true); setError(null)
    try {
      const r = await axios.post('/api/pexels/search', { query: sq, per_page: 12 })
      setResults(r.data.results || [])
    } catch(e) { setError(e.response?.data?.detail || String(e)) }
    setBusy(false)
  }

  useEffect(() => { if (initialQuery) search(initialQuery) }, [])

  const pick = async (photo) => {
    setBusy(true)
    try {
      const r = await axios.post('/api/pexels/download', {
        url: photo.full_url, folder_path: folderPath, section,
      })
      onSelect({ path: r.data.path, preview: photo.preview_url, credit: photo.photographer })
    } catch(e) { setError(String(e)) }
    setBusy(false)
  }

  return (
    <div style={{position:'fixed',inset:0,background:'rgba(0,0,0,0.82)',display:'flex',alignItems:'center',justifyContent:'center',zIndex:3000}} onClick={onClose}>
      <div style={{background:'var(--bg-card)',border:'1px solid var(--border)',borderRadius:'var(--radius)',width:740,maxWidth:'95vw',maxHeight:'86vh',display:'flex',flexDirection:'column'}} onClick={e=>e.stopPropagation()}>
        <div style={{display:'flex',alignItems:'center',gap:10,padding:'14px 18px',borderBottom:'1px solid var(--border)'}}>
          <span style={{fontWeight:700,fontSize:14,flex:1}}>🖼️ Pexels — {section}</span>
          <button className="btn btn-ghost btn-sm" onClick={onClose} style={{padding:4}}><X size={14}/></button>
        </div>
        <div style={{display:'flex',gap:8,padding:'12px 18px',borderBottom:'1px solid var(--border)'}}>
          <input type="text" value={query} style={{flex:1}} placeholder="Search Pexels…"
            onChange={e => setQuery(e.target.value)}
            onKeyDown={e => e.key==='Enter' && search()} />
          <button className="btn btn-primary btn-sm" disabled={busy||!query.trim()} onClick={() => search()}>
            {busy ? <RefreshCw size={13} style={{animation:'spin 1s linear infinite'}}/> : 'Search'}
          </button>
        </div>
        <div style={{flex:1,overflowY:'auto',padding:14}}>
          {error && <div className="alert alert-error" style={{marginBottom:10}}>{error}</div>}
          {results.length===0 && !busy && (
            <div style={{textAlign:'center',color:'var(--text-subtle)',padding:32,fontSize:13}}>
              {initialQuery ? 'No results — try a different query' : 'Search for images above'}
            </div>
          )}
          <div style={{display:'grid',gridTemplateColumns:'repeat(auto-fill,minmax(190px,1fr))',gap:8}}>
            {results.map(p => (
              <div key={p.id}
                style={{cursor:'pointer',borderRadius:8,overflow:'hidden',border:'2px solid transparent',transition:'border-color 0.15s'}}
                onMouseEnter={e=>e.currentTarget.style.borderColor='var(--accent)'}
                onMouseLeave={e=>e.currentTarget.style.borderColor='transparent'}
                onClick={() => pick(p)}>
                <img src={p.preview_url} alt={p.alt||''} style={{width:'100%',height:120,objectFit:'cover',display:'block'}}/>
                <div style={{padding:'4px 6px',fontSize:10,color:'var(--text-subtle)',background:'var(--bg-elevated)'}}>📷 {p.photographer}</div>
              </div>
            ))}
          </div>
        </div>
        <div style={{padding:'8px 18px',borderTop:'1px solid var(--border)',fontSize:11,color:'var(--text-subtle)'}}>
          Photos from <a href="https://www.pexels.com" target="_blank" rel="noreferrer" style={{color:'var(--accent)'}}>Pexels</a> — free to use
        </div>
      </div>
    </div>
  )
}

/* ══ PHASE 2 ══════════════════════════════════════════════════ */
function Phase2({ projectId }) {
  const { outputData, subtitleMode, setSubtitleMode, setPhase, channelTemplate } = usePipeline()

  const mkBg = () => ({ file: null, path: null, preview: null, credit: null })
  const [bgs,        setBgs]        = useState({})
  const [log,        setLog]        = useState([])
  const [prog,       setProg]       = useState(0)
  const [vpath,      setVpath]      = useState(null)
  const [vhash,      setVhash]      = useState(Date.now())
  const [busy,       setBusy]       = useState(false)
  const [pexBusy,    setPexBusy]    = useState(false)
  const [pexQueries, setPexQueries] = useState({})
  const [picker,     setPicker]     = useState(null)
  const [noKey,      setNoKey]      = useState(false)
  // Contextual mode
  const [ctxMode,    setCtxMode]    = useState(false)   // true = contextual, false = simple
  const [ctxBusy,    setCtxBusy]    = useState(false)
  const [timelines,  setTimelines]  = useState(null)    // { node: [{query,path,char_count}, ...] }
  const logRef = useRef(null)

  useEffect(() => { if (logRef.current) logRef.current.scrollTop = logRef.current.scrollHeight }, [log])
  const addLog = l => setLog(p => [...p, l])
  const sections = outputData?.sections || {}

  useEffect(() => {
    axios.get('/api/pexels/key-status')
      .then(r => setNoKey(!r.data.configured))
      .catch(() => setNoKey(true))
  }, [])

  useEffect(() => {
    if (outputData?.folder_path) {
      const vp = outputData.folder_path + '/master_video.mp4'
      fetch(`/api/video-file/${encodeURIComponent(vp)}`, {method:'HEAD'})
        .then(r => { if (r.ok) setVpath(vp) }).catch(() => {})
    }
  }, [])

  const autoFetch = async () => {
    setPexBusy(true)
    addLog({ type:'status', text:'🔍 LLM extracting visual keywords → searching Pexels…' })
    try {
      const r = await axios.post('/api/pexels/auto', {
        topic: outputData.topic, 
        sections, 
        folder_path: outputData.folder_path,
        channel_template: channelTemplate
      })
      setPexQueries(r.data.queries || {})
      const paths = r.data.paths || {}
      setBgs(prev => {
        const next = { ...prev }
        for (const [sec, path] of Object.entries(paths)) {
          next[sec] = { file: null, path, preview: null, credit: 'Pexels' }
          addLog({ type:'success', text:`✅ ${sec}: "${r.data.queries?.[sec] || ''}"` })
        }
        return next
      })
    } catch(e) {
      addLog({ type:'error', text:`❌ ${e.response?.data?.detail || e}` })
    }
    setPexBusy(false)
  }

  const contextualFetch = async () => {
    setCtxBusy(true)
    addLog({ type:'status', text:'🎬 Building contextual timeline — LLM analysing each paragraph…' })
    try {
      const r = await axios.post('/api/pexels/contextual', {
        topic:               outputData.topic,
        sections,
        folder_path:         outputData.folder_path,
        sentences_per_chunk: 4,
        channel_template:    channelTemplate
      })
      setTimelines(r.data.timelines)
      const total = Object.values(r.data.timelines).reduce((s, arr) => s + arr.length, 0)
      addLog({ type:'success', text:`✅ ${total} contextual images ready across all sections` })
      setCtxMode(true)
    } catch(e) {
      addLog({ type:'error', text:`❌ ${e.response?.data?.detail || e}` })
    }
    setCtxBusy(false)
  }

  const render = async () => {
    setBusy(true); setLog([]); setProg(0); setVpath(null)
    const fd = new FormData()
    fd.append('topic_dir',    outputData.folder_path)
    fd.append('script_json',  JSON.stringify(outputData))
    fd.append('subtitle_mode', subtitleMode)
    fd.append('project_id',   String(projectId || ''))

    if (ctxMode && timelines) {
      // Pass the full contextual timeline JSON
      fd.append('bg_timelines_json', JSON.stringify(timelines))
    } else {
      // Simple mode — pass individual bg files / paths
      for (const [sec, bg] of Object.entries(bgs)) {
        if (bg.file)      fd.append(`bg_${sec}`, bg.file)
        else if (bg.path) fd.append(`bg_${sec}_path`, bg.path)
      }
    }
    await readSSE('/api/render-video', {method:'POST', body:fd}, (e) => {
      if (e.type==='progress') { setProg(e.total>0 ? Math.round(e.current/e.total*100) : 0); addLog({type:'status', text:e.message}) }
      else if (e.type==='complete') { setVpath(e.video_path); setVhash(Date.now()); setProg(100); addLog({type:'success', text:'✅ Video ready!'}) }
      else if (e.type==='error')    addLog({type:'error', text:`❌ ${e.data}`})
    })
    setBusy(false)
  }

  const cancelRender = async () => {
    try {
      await axios.post('/api/cancel-render', { topic_dir: outputData.folder_path })
      addLog({type:'status', text:'🛑 Cancellation requested...'})
    } catch(e) {
      console.error(e)
    }
  }

  return (
    <div>
      {picker && (
        <PexelsPicker
          section={picker.section}
          initialQuery={pexQueries[picker.section] || picker.section}
          folderPath={outputData.folder_path}
          onSelect={v => { setBgs(p => ({...p, [picker.section]: {...v, file:null}})); setPicker(null) }}
          onClose={() => setPicker(null)}
        />
      )}

      <details className="card" style={{marginBottom:14}}>
        <summary style={{cursor:'pointer', fontWeight:600, color:'var(--text-muted)'}}>📄 Full Script</summary>
        <div style={{marginTop:12, display:'flex', flexDirection:'column', gap:12}}>
          {Object.entries(sections).map(([key, text]) => {
            const lbl = Object.values(TEMPLATES).flat().find(n => n.key === key)?.label || key
            return (
              <div key={key}><div className="node-label">{lbl}</div><div className="node-text" style={{fontSize:13}}>{text}</div></div>
            )
          })}
        </div>
      </details>

      <div className="card">
        <div style={{display:'flex',gap:12,marginBottom:16}}>
          <div style={{flex:1,display:'flex',borderRadius:8,overflow:'hidden',border:'1px solid var(--border)'}}>
            {[['simple','🖼️ Simple (3 images)'],['contextual','🎬 Contextual (smart)']].map(([mode, label]) => (
              <button key={mode}
                style={{flex:1,padding:'9px 0',fontSize:12,fontWeight:600,border:'none',cursor:'pointer',
                  background: (mode==='contextual'?ctxMode:!ctxMode) ? 'var(--accent)' : 'var(--bg-elevated)',
                  color:      (mode==='contextual'?ctxMode:!ctxMode) ? '#000' : 'var(--text-muted)',
                  transition:'all 0.15s'}}
                onClick={() => setCtxMode(mode==='contextual')}>
                {label}
              </button>
            ))}
          </div>
          
          <div style={{flex:1,display:'flex',alignItems:'center',gap:8,padding:'0 12px',background:'var(--bg-elevated)',borderRadius:8,border:'1px solid var(--border)'}}>
            <span style={{fontSize:12,fontWeight:600,color:'var(--text-muted)'}}>📝 Subtitles:</span>
            <select style={{flex:1,border:'none',background:'transparent',fontSize:12,fontWeight:600,cursor:'pointer',outline:'none'}}
                    value={subtitleMode} onChange={e => setSubtitleMode(e.target.value)}>
              <option value="chunk">Chunk (Dynamic 5-8 words)</option>
              <option value="word">Word (TikTok style)</option>
              <option value="sentence">Sentence (Classic)</option>
            </select>
          </div>
        </div>

        {noKey && <div style={{marginBottom:12,fontSize:11,color:'var(--red)',padding:'8px 10px',background:'rgba(255,80,80,0.08)',borderRadius:6}}>⚠️ Set PEXELS_API_KEY in config.py to enable Pexels features</div>}

        {/* ── SIMPLE MODE ──────────────────────────────────────────── */}
        {!ctxMode && (<>
          <div style={{display:'flex',alignItems:'center',gap:10,marginBottom:14,padding:'8px 12px',background:'var(--bg-elevated)',borderRadius:6,border:'1px solid var(--border)'}}>
            <div style={{flex:1,fontSize:12,color:'var(--text-muted)'}}>One image per section (Thesis / Antithesis / Synthesis)</div>
            {!noKey && <button className="btn btn-secondary btn-sm" disabled={pexBusy||busy} onClick={autoFetch}>
              {pexBusy ? <><RefreshCw size={12} style={{animation:'spin 1s linear infinite'}}/> Fetching…</> : '✨ Auto-fetch'}
            </button>}
          </div>
          <div style={{display:'grid',gridTemplateColumns:'repeat(auto-fill,minmax(220px,1fr))',gap:12,marginBottom:16}}>
            {Object.keys(sections).filter(k => k !== 'hook' && !k.startsWith('bridge')).map(k => {
              const bg = bgs[k] || mkBg()
              const hasBg = bg.preview || bg.path
              const lbl = Object.values(TEMPLATES).flat().find(n => n.key === k)?.label || k
              return (
                <div key={k} style={{background:'var(--bg-elevated)',borderRadius:8,overflow:'hidden',border:'1px solid var(--border)'}}>
                  <div style={{position:'relative',height:120,background:'#111',display:'flex',alignItems:'center',justifyContent:'center'}}>
                    {hasBg ? (<>
                      <img src={bg.preview || `/api/video-file/${encodeURIComponent(bg.path)}`}
                        alt="" style={{width:'100%',height:'100%',objectFit:'cover',display:'block'}} onError={e=>e.target.style.display='none'}/>
                      <button onClick={() => setBgs(p=>({...p,[k]:mkBg()}))}
                        style={{position:'absolute',top:4,right:4,background:'rgba(0,0,0,0.65)',border:'none',borderRadius:99,padding:'2px 7px',cursor:'pointer',color:'#fff',fontSize:11}}>✕</button>
                    </>) : <span style={{color:'var(--text-subtle)',fontSize:12}}>No image</span>}
                  </div>
                  <div style={{padding:'6px 10px 2px',fontWeight:600,fontSize:12}}>{lbl}</div>
                  {pexQueries[k] && <div style={{padding:'0 10px 4px',fontSize:10,color:'var(--accent)',fontStyle:'italic'}}>"{pexQueries[k]}"</div>}
                  <div style={{display:'flex',gap:6,padding:'6px 10px 10px'}}>
                    <button className="btn btn-secondary btn-sm" style={{flex:1,fontSize:11}} disabled={noKey||busy}
                      onClick={() => setPicker({section:k})}>🔍 Pexels</button>
                    <label className="btn btn-ghost btn-sm" style={{flex:1,fontSize:11,justifyContent:'center',margin:0,padding:'4px 8px',cursor:'pointer'}}>
                      📁 Upload
                      <input type="file" accept="image/*" style={{display:'none'}}
                        onChange={e => { const f=e.target.files[0]; if(f) setBgs(p=>({...p,[k]:{file:f,path:null,preview:URL.createObjectURL(f),credit:null}})) }}/>
                    </label>
                  </div>
                </div>
              )
            })}
          </div>
        </>)}

        {/* ── CONTEXTUAL MODE ──────────────────────────────────────── */}
        {ctxMode && (<>
          <div style={{display:'flex',alignItems:'center',gap:12,marginBottom:14,padding:'10px 14px',background:'var(--bg-elevated)',borderRadius:8,border:'1px solid var(--border)'}}>
            <div style={{flex:1}}>
              <div style={{fontWeight:600,fontSize:13}}>🎬 Contextual Backgrounds</div>
              <div style={{fontSize:11,color:'var(--text-muted)',marginTop:2}}>
                LLM reads every ~4 sentences → unique Pexels image per thought → smooth crossfade
              </div>
            </div>
            {!noKey && <button className="btn btn-primary btn-sm" disabled={ctxBusy||busy} onClick={contextualFetch}>
              {ctxBusy ? <><RefreshCw size={12} style={{animation:'spin 1s linear infinite'}}/> Analysing…</> : timelines ? '🔄 Regenerate' : '🎬 Generate'}
            </button>}
          </div>

          {timelines && (
            <div style={{display:'flex',flexDirection:'column',gap:12,marginBottom:16}}>
              {Object.entries(timelines).map(([node, items]) => (
                <div key={node}>
                  <div style={{fontSize:11,fontWeight:700,color:'var(--text-muted)',textTransform:'uppercase',letterSpacing:'0.06em',marginBottom:6}}>
                    {node.replace('_',' ')} — {items.length} image{items.length!==1?'s':''}
                  </div>
                  <div style={{display:'flex',gap:4,overflowX:'auto',paddingBottom:4}}>
                    {items.map((item, i) => (
                      <div key={i} style={{flexShrink:0,width:90,borderRadius:6,overflow:'hidden',border:'1px solid var(--border)'}}>
                        <img src={`/api/video-file/${encodeURIComponent(item.path)}`}
                          alt={item.query} style={{width:'100%',height:56,objectFit:'cover',display:'block'}}
                          onError={e=>e.target.style.display='none'}/>
                        <div style={{padding:'2px 4px',fontSize:9,color:'var(--text-subtle)',background:'var(--bg-elevated)',overflow:'hidden',textOverflow:'ellipsis',whiteSpace:'nowrap'}}
                          title={item.query}>{item.query}</div>
                      </div>
                    ))}
                  </div>
                </div>
              ))}
            </div>
          )}

          {!timelines && !ctxBusy && (
            <div style={{textAlign:'center',padding:'24px 0',color:'var(--text-subtle)',fontSize:13,marginBottom:16}}>
              Click <strong>Generate</strong> to let the LLM build a full visual story for your script
            </div>
          )}
        </>)}

        <hr className="divider"/>
        {prog > 0 && <div style={{marginBottom:10}}><div className="progress-wrap"><div className="progress-bar" style={{width:`${prog}%`}}/></div><span style={{fontSize:11, color:'var(--text-muted)'}}>{prog}%</span></div>}
        {log.length > 0 && <div className="sse-log" ref={logRef} style={{marginBottom:12}}>{log.map((l,i) => <div key={i} className={`log-${l.type}`}>{l.text}</div>)}</div>}
        
        {busy ? (
          <div style={{display:'flex', gap:10}}>
            <button className="btn btn-primary" style={{flex:1, justifyContent:'center', opacity: 0.7}} disabled={true}>
              <RefreshCw size={14} style={{animation:'spin 1s linear infinite'}}/> Rendering…
            </button>
            <button className="btn" style={{background:'var(--red)', color:'#fff', border:'none', padding:'0 16px', fontWeight:600}} onClick={cancelRender}>
              🛑 Stop
            </button>
          </div>
        ) : (
          <button className="btn btn-primary" style={{width:'100%', justifyContent:'center'}} onClick={render}>
            🎬 Render Video
          </button>
        )}

        {vpath && (
          <div style={{marginTop:14}}>
            <video controls style={{width:'100%', borderRadius:8, marginBottom:10}}
              src={`/api/video-file/${encodeURIComponent(vpath)}?t=${vhash}`} />
            <button className="btn btn-secondary" style={{width:'100%', justifyContent:'center'}} onClick={() => setPhase(3)}>
              Continue to YouTube <ChevronRight size={14}/>
            </button>
          </div>
        )}
      </div>
    </div>
  )
}

/* ══ PHASE 3 ══════════════════════════════════════════════════ */
function Phase3({ projectId }) {
  const { outputData, ytMeta, setYtMeta, ytResult, setYtResult, channelTemplate } = usePipeline()
  const [busy,       setBusy]       = useState(false)
  const [rBusy,      setRBusy]      = useState(false)
  const [log,        setLog]        = useState([])
  const [prog,       setProg]       = useState(0)
  const [thumb,      setThumb]      = useState(null)
  const [thumbPrev,  setThumbPrev]  = useState(null)
  const [hdd,        setHdd]        = useState('')
  const [showBrowse, setShowBrowse] = useState(false)
  const [meta,       setMeta]       = useState(null)
  const [channel,    setChannel]    = useState(channelTemplate || 'still_point')
  const logRef = useRef(null)

  useEffect(() => { if (ytMeta) setMeta({...ytMeta}) }, [ytMeta])
  useEffect(() => { if (logRef.current) logRef.current.scrollTop = logRef.current.scrollHeight }, [log])
  const addLog = l => setLog(p => [...p, l])

  const research = async () => {
    setRBusy(true)
    try {
      const r = await axios.post('/api/yt/metadata', { topic: outputData.topic, script_data: outputData })
      setYtMeta(r.data); setMeta({...r.data})
    } catch(e) { addLog({type:'error', text:String(e)}) }
    setRBusy(false)
  }

  const upload = async () => {
    setBusy(true); setLog([]); setProg(0)
    const fd = new FormData()
    fd.append('video_path',  outputData.folder_path + '/master_video.mp4')
    fd.append('topic_dir',   outputData.folder_path)
    fd.append('title',       meta.title)
    fd.append('description', meta.description)
    fd.append('tags_json',   JSON.stringify((meta.tags||[]).filter(Boolean)))
    fd.append('category_id', meta.category_id || '27')
    fd.append('privacy',     meta.privacy || 'private')
    fd.append('language',    meta.language || 'en')
    fd.append('playlist_id', meta.playlist_id || '')
    fd.append('hdd_path',    hdd)
    fd.append('project_id',  String(projectId || ''))
    fd.append('channel_name', channel)
    if (thumb) fd.append('thumbnail', thumb)

    await readSSE('/api/yt/upload', {method:'POST', body:fd}, (e) => {
      if (e.type==='status')   addLog({type:'status', text: e.data})
      else if (e.type==='progress') { setProg(e.total>0 ? Math.round(e.sent/e.total*100) : 0) }
      else if (e.type==='complete') { setYtResult(e.data); setProg(100); addLog({type:'success', text:`✅ ${e.data.url}`}) }
      else if (e.type==='error')    addLog({type:'error', text:`❌ ${e.data}`})
    })
    setBusy(false)
  }

  return (
    <div>
      {showBrowse && <FolderBrowser onSelect={(p) => { setHdd(p); setShowBrowse(false) }} onClose={() => setShowBrowse(false)} />}

      {/* ── Thumbnail — always visible, no need to research first ── */}
      <div className="card" style={{marginBottom:14}}>
        <div className="card-title">🖼️ Thumbnail (1280×720 recommended)</div>
        <label className="upload-zone" style={{marginBottom: thumbPrev ? 10 : 0}}>
          <input type="file" accept="image/*" onChange={e => {
            const f = e.target.files[0]
            if (!f) return
            setThumb(f); setThumbPrev(URL.createObjectURL(f))
          }}/>
          {thumb
            ? <span style={{color:'var(--green)'}}>✓ {thumb.name}</span>
            : <span>Click or drag thumbnail image here</span>}
        </label>
        {thumbPrev && (
          <div style={{position:'relative',display:'inline-block'}}>
            <img src={thumbPrev} style={{width:240,borderRadius:8,display:'block'}} alt="thumbnail preview"/>
            <button
              onClick={() => { setThumb(null); setThumbPrev(null) }}
              style={{position:'absolute',top:6,right:6,background:'rgba(0,0,0,0.6)',border:'none',borderRadius:99,padding:'3px 6px',cursor:'pointer',color:'#fff',fontSize:12}}
            >✕</button>
          </div>
        )}
      </div>

      {/* ── Research + Metadata ─────────────────────────────────── */}
      <div className="card">
        <button className="btn btn-secondary" disabled={rBusy} onClick={research}>
          {rBusy ? <><RefreshCw size={13} style={{animation:'spin 1s linear infinite'}}/> Researching…</> : '🔍 Research Metadata'}
        </button>
      </div>

      {meta && (
        <div className="card">
          <div className="input-group"><label>Title</label>
            <input type="text" maxLength={100} value={meta.title||''} onChange={e => setMeta(m => ({...m, title:e.target.value}))}/>
          </div>
          <div className="input-group"><label>Description</label>
            <textarea rows={4} value={meta.description||''} onChange={e => setMeta(m => ({...m, description:e.target.value}))}/>
          </div>
          <div className="input-group"><label>Tags (comma-separated)</label>
            <input type="text" value={(meta.tags||[]).join(', ')} onChange={e => setMeta(m => ({...m, tags:e.target.value.split(',').map(t=>t.trim())}))}/>
          </div>
          <div className="row" style={{marginBottom:14}}>
            <div className="input-group" style={{margin:0, flex:1}}>
              <label>Target Channel</label>
              <select value={channel} onChange={e => setChannel(e.target.value)}>
                <option value="still_point">⚖️ Still Point</option>
                <option value="zerourgency">📺 ZeroUrgency</option>
              </select>
            </div>
            <div className="alert alert-info" style={{margin:0, flex:1, display:'flex', alignItems:'center', justifyContent:'center'}}>🏷️ {meta.category_name} ({meta.category_id})</div>
            <div className="alert alert-info" style={{margin:0, flex:1, display:'flex', alignItems:'center', justifyContent:'center'}}>🇬🇧 English (en)</div>
          </div>
          <div className="row">
            <div className="input-group"><label>Privacy</label>
              <select value={meta.privacy||'private'} onChange={e => setMeta(m => ({...m, privacy:e.target.value}))}>
                <option value="private">🔒 Private</option>
                <option value="unlisted">🔗 Unlisted</option>
                <option value="public">🌐 Public</option>
              </select>
            </div>
            <div className="input-group"><label>Playlist ID (optional)</label>
              <input type="text" placeholder="PLxxxxxxxxxxxxxx" value={meta.playlist_id||''} onChange={e => setMeta(m => ({...m, playlist_id:e.target.value}))}/>
            </div>
          </div>
          <div className="input-group"><label>💾 Archive to Drive (optional)</label>
            <div style={{display:'flex',gap:8}}>
              <input
                type="text"
                placeholder="/media/vaasu/MyHDD — or browse →"
                value={hdd}
                onChange={e => setHdd(e.target.value)}
                style={{flex:1}}
              />
              <button className="btn btn-secondary btn-sm" style={{flexShrink:0,whiteSpace:'nowrap'}} onClick={() => setShowBrowse(true)}>
                <FolderOpen size={13}/> Browse
              </button>
            </div>
            {hdd && <div style={{fontSize:11,color:'var(--green)',marginTop:4}}>📁 {hdd}</div>}
          </div>

          {prog > 0 && <div style={{marginBottom:10}}><div className="progress-wrap"><div className="progress-bar" style={{width:`${prog}%`}}/></div><span style={{fontSize:11, color:'var(--text-muted)'}}>{prog}%</span></div>}
          {log.length > 0 && <div className="sse-log" ref={logRef} style={{marginBottom:12}}>{log.map((l,i) => <div key={i} className={`log-${l.type}`}>{l.text}</div>)}</div>}

          <button className="btn btn-primary" style={{width:'100%', justifyContent:'center'}}
            disabled={busy || !meta?.title} onClick={upload}>
            {busy ? <><RefreshCw size={13} style={{animation:'spin 1s linear infinite'}}/> Uploading…</> : '🚀 Upload to YouTube'}
          </button>

          {ytResult && (
            <div className="alert alert-success" style={{marginTop:12}}>
              🎉 <a href={ytResult.url} target="_blank" rel="noreferrer" style={{color:'var(--green)'}}>{ytResult.url}</a>
            </div>
          )}
        </div>
      )}
    </div>
  )
}

/* ══ Main Generator page ══════════════════════════════════════ */
export default function Generator() {
  const { id }     = useParams()
  const projectId  = id ? parseInt(id) : null
  const navigate   = useNavigate()
  const { topic, phase, setPhase, loadProject, outputData } = usePipeline()

  // On mount: if we have a projectId but no outputData, load the project from API
  useEffect(() => {
    if (projectId && !outputData) {
      axios.get(`/api/projects/${projectId}`)
        .then(r => loadProject(r.data))
        .catch(() => navigate('/projects'))
    }
  }, [projectId])

  const phaseLabels = ['1 · Script & Audio', '2 · Video', '3 · YouTube']

  return (
    <div>
      <div className="page-header" style={{display:'flex', justifyContent:'space-between', alignItems:'flex-end'}}>
        <div>
          <button className="btn btn-ghost btn-sm" style={{marginBottom:6, padding:'4px 0'}}
            onClick={() => navigate('/projects')}>
            <ArrowLeft size={14}/> All Projects
          </button>
          <h2 style={{fontFamily:'var(--font-serif)'}}>{topic || 'New Project'}</h2>
        </div>
      </div>

      {/* Phase stepper */}
      <div className="phase-steps" style={{marginBottom:24}}>
        {phaseLabels.map((label, i) => (
          <div key={i} className={`phase-step ${phase === i+1 ? 'active' : phase > i+1 ? 'done' : ''}`}>
            {label}
          </div>
        ))}
      </div>

      {phase === 1 && <Phase1 projectId={projectId} />}
      {phase === 2 && <Phase2 projectId={projectId} />}
      {phase === 3 && <Phase3 projectId={projectId} />}
    </div>
  )
}
