import { useState, useEffect } from 'react'
import { Trash2, ChevronDown, ChevronUp } from 'lucide-react'
import usePipeline from '../store/pipeline'
import { useNavigate } from 'react-router-dom'
import axios from 'axios'

const NODES = [
  {key:'hook',label:'Hook'},{key:'thesis',label:'Thesis'},{key:'bridge_ab',label:'Bridge A→B'},
  {key:'antithesis',label:'Antithesis'},{key:'bridge_bc',label:'Bridge B→C'},{key:'synthesis',label:'Synthesis'},
]

async function readSSE(url, opts, onEvent) {
  const res = await fetch(url, opts)
  const reader = res.body.getReader(); const dec = new TextDecoder(); let buf = ''
  while (true) {
    const {done,value} = await reader.read(); if (done) break
    buf += dec.decode(value,{stream:true})
    const parts = buf.split('\n\n'); buf = parts.pop()
    for (const p of parts) {
      const line = p.replace(/^data: /,''); if (!line.trim()) continue
      try { onEvent(JSON.parse(line)) } catch(_) {}
    }
  }
}

function LibraryEntry({ script, onDelete }) {
  const [open, setOpen]       = useState(false)
  const [meta, setMeta]       = useState(null)
  const [rBusy, setRBusy]     = useState(false)
  const [uBusy, setUBusy]     = useState(false)
  const [log, setLog]         = useState([])
  const [prog, setProg]       = useState(0)
  const [thumb, setThumb]     = useState(null)
  const [channel, setChannel] = useState('channel_1')
  const [hdd, setHdd]         = useState('')
  const [result, setResult]   = useState(null)
  const { setTopic, setPhase, resetForNew } = usePipeline()
  const navigate = useNavigate()
  const addLog = l => setLog(p => [...p, l])

  const useAsTopic = () => {
    resetForNew()
    setTopic(script.script_data?.topic || '')
    setPhase(1)
    navigate('/generator')
  }

  const research = async () => {
    setRBusy(true)
    try {
      const r = await axios.post('/api/yt/metadata', {
        topic: script.script_data?.topic, script_data: script.script_data
      })
      setMeta({ ...r.data })
    } catch(e) { addLog({type:'error',text:String(e)}) }
    setRBusy(false)
  }

  const upload = async () => {
    setUBusy(true); setLog([]); setProg(0)
    const fd = new FormData()
    fd.append('video_path',  script.video_path)
    fd.append('topic_dir',   script.topic_dir)
    fd.append('title',       meta.title); fd.append('description', meta.description)
    fd.append('tags_json',   JSON.stringify((meta.tags||[]).filter(Boolean)))
    fd.append('category_id', meta.category_id||'27'); fd.append('privacy', meta.privacy||'private')
    fd.append('language',    meta.language||'en'); fd.append('playlist_id', meta.playlist_id||'')
    fd.append('hdd_path',    hdd)
    fd.append('channel_name', channel)
    if (thumb) fd.append('thumbnail', thumb)
    await readSSE('/api/yt/upload',{method:'POST',body:fd},(e)=>{
      if(e.type==='status')  addLog({type:'status',text:e.data})
      else if(e.type==='progress'){setProg(e.total>0?Math.round(e.sent/e.total*100):0)}
      else if(e.type==='complete'){setResult(e.data);setProg(100);addLog({type:'success',text:`✅ ${e.data.url}`})}
      else if(e.type==='error')  addLog({type:'error',text:`❌ ${e.data}`})
    })
    setUBusy(false)
  }

  const sd = script.script_data || {}

  return (
    <div className="library-entry">
      <div className="library-entry-header" onClick={() => setOpen(o => !o)}>
        <div>
          <strong style={{fontSize:15}}>{sd.topic || script.topic}</strong>
          <div style={{fontSize:12,color:'var(--text-muted)',marginTop:2}}>{script.date} · {sd.word_count} words
            {script.has_video && <span className="badge badge-green" style={{marginLeft:8}}>🎬 Video</span>}
          </div>
        </div>
        <div style={{display:'flex',gap:8,alignItems:'center'}}>
          <button className="btn btn-ghost btn-sm" onClick={e=>{e.stopPropagation();useAsTopic()}}>Use topic</button>
          <button className="btn btn-danger btn-sm" onClick={e=>{e.stopPropagation();onDelete(script.id)}}>
            <Trash2 size={13}/>
          </button>
          {open ? <ChevronUp size={16}/> : <ChevronDown size={16}/>}
        </div>
      </div>

      {open && (
        <div className="library-entry-body">
          {/* Script sections */}
          <details style={{marginBottom:14}}>
            <summary style={{cursor:'pointer',fontWeight:600,color:'var(--text-muted)',fontSize:13}}>📄 Script</summary>
            <div style={{marginTop:10,display:'flex',flexDirection:'column',gap:10}}>
              {NODES.map(n=>sd.sections?.[n.key]?(<div key={n.key}><div className="node-label">{n.label}</div><div className="node-text" style={{fontSize:12}}>{sd.sections[n.key]}</div></div>):null)}
            </div>
          </details>

          {/* Audio */}
          {script.audio_nodes?.length > 0 && (
            <details style={{marginBottom:14}}>
              <summary style={{cursor:'pointer',fontWeight:600,color:'var(--text-muted)',fontSize:13}}>🎙️ Audio</summary>
              <div style={{marginTop:10,display:'flex',flexDirection:'column',gap:6}}>
                {script.audio_nodes.map(a=>(
                  <div key={a.node}>
                    <div style={{fontSize:11,color:'var(--text-subtle)',marginBottom:2}}>{a.node.replace('_',' → ')}</div>
                    <audio controls src={`/api/audio/${encodeURIComponent(a.path)}`}/>
                  </div>
                ))}
              </div>
            </details>
          )}

          {/* Video */}
          {script.has_video && (
            <div style={{marginBottom:14}}>
              <div className="card-title">🎬 Video</div>
              <video controls style={{width:'100%',borderRadius:8}} src={`/api/video-file/${encodeURIComponent(script.video_path)}`}/>
            </div>
          )}

          {/* YouTube Upload */}
          {script.has_video && (
            <div style={{borderTop:'1px solid var(--border)',paddingTop:14}}>
              <div className="card-title">📤 Upload to YouTube</div>
              <button className="btn btn-secondary btn-sm" disabled={rBusy} onClick={research} style={{marginBottom:12}}>
                {rBusy?'Researching…':'🔍 Research Metadata'}
              </button>
              {meta && (
                <div style={{display:'flex',flexDirection:'column',gap:8}}>
                  <input type="text" value={meta.title||''} onChange={e=>setMeta(m=>({...m,title:e.target.value}))} placeholder="Title"/>
                  <textarea rows={3} value={meta.description||''} onChange={e=>setMeta(m=>({...m,description:e.target.value}))} placeholder="Description" style={{fontSize:12}}/>
                  <input type="text" value={(meta.tags||[]).join(', ')} onChange={e=>setMeta(m=>({...m,tags:e.target.value.split(',').map(t=>t.trim())}))} placeholder="Tags"/>
                  <div className="row">
                    <select value={meta.privacy||'private'} onChange={e=>setMeta(m=>({...m,privacy:e.target.value}))}>
                      <option value="private">🔒 Private</option><option value="unlisted">🔗 Unlisted</option><option value="public">🌐 Public</option>
                    </select>
                    <select value={channel} onChange={e=>setChannel(e.target.value)}>
                      <option value="channel_1">Channel 1</option>
                      <option value="channel_2">Channel 2</option>
                    </select>
                    <input type="text" placeholder="Playlist ID (optional)" value={meta.playlist_id||''} onChange={e=>setMeta(m=>({...m,playlist_id:e.target.value}))}/>
                  </div>
                  <label className="upload-zone" style={{padding:10}}>
                    <input type="file" accept="image/*" onChange={e=>setThumb(e.target.files[0])}/>
                    {thumb?<span style={{color:'var(--green)'}}>✓ {thumb.name}</span>:<span style={{fontSize:12}}>Upload Thumbnail</span>}
                  </label>
                  <input type="text" placeholder="HDD path (optional)" value={hdd} onChange={e=>setHdd(e.target.value)}/>
                  {prog>0&&<div className="progress-wrap"><div className="progress-bar" style={{width:`${prog}%`}}/></div>}
                  {log.length>0&&<div className="sse-log" style={{maxHeight:120}}>{log.map((l,i)=><div key={i} className={`log-${l.type}`}>{l.text}</div>)}</div>}
                  <button className="btn btn-primary btn-sm" disabled={uBusy||!meta.title} onClick={upload}>
                    {uBusy?'Uploading…':'🚀 Upload to YouTube'}
                  </button>
                  {result&&<div className="alert alert-success"><a href={result.url} target="_blank" rel="noreferrer" style={{color:'var(--green)'}}>{result.url}</a></div>}
                </div>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  )
}

export default function Library() {
  const [scripts, setScripts] = useState([])
  const [loading, setLoading] = useState(true)

  const load = async () => {
    setLoading(true)
    try { const r = await axios.get('/api/library'); setScripts(r.data) }
    catch(_) {}
    setLoading(false)
  }

  const deleteEntry = async (id) => {
    await axios.delete(`/api/library/${id}`)
    setScripts(s => s.filter(x => x.id !== id))
  }

  useEffect(() => { load() }, [])

  return (
    <div>
      <div className="page-header">
        <h2>Script Library</h2>
        <p>All generated scripts with audio, video, and YouTube upload.</p>
      </div>
      {loading ? <p style={{color:'var(--text-muted)'}}>Loading…</p>
        : scripts.length === 0 ? <div className="alert alert-info">No scripts yet. Generate one in the Generator tab.</div>
        : scripts.map(s => <LibraryEntry key={s.id} script={s} onDelete={deleteEntry} />)
      }
    </div>
  )
}
