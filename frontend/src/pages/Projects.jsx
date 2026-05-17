import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  Plus, Trash2, ChevronRight, Youtube, Video, FileText,
  Loader, X, ChevronUp, ArrowLeft, Move,
} from 'lucide-react'
import usePipeline from '../store/pipeline'
import axios from 'axios'
import FolderBrowser from '../components/FolderBrowser'

// ── Phase config ───────────────────────────────────────────────
const PHASES = {
  drafting:    { label: 'Generating…',  color: 'var(--accent)', bg: 'var(--accent-glow)',     icon: <Loader size={12} style={{animation:'spin 1s linear infinite'}}/> },
  script_done: { label: 'Script Ready', color: '#f0c060',       bg: 'rgba(240,192,96,0.12)',  icon: <FileText size={12}/> },
  video_done:  { label: 'Video Ready',  color: '#3dd68c',       bg: 'rgba(61,214,140,0.12)',  icon: <Video size={12}/> },
  published:   { label: 'Published',    color: '#ff7070',       bg: 'rgba(255,112,112,0.12)', icon: <Youtube size={12}/> },
}

function PhaseBadge({ phase }) {
  const p = PHASES[phase] || PHASES.script_done
  return (
    <span style={{display:'inline-flex',alignItems:'center',gap:5,background:p.bg,color:p.color,padding:'3px 10px',borderRadius:99,fontSize:12,fontWeight:600}}>
      {p.icon} {p.label}
    </span>
  )
}

// ── Project Detail Panel ───────────────────────────────────────
function ProjectDetail({ project, onClose, onMoved }) {
  const [showBrowser, setShowBrowser]   = useState(false)
  const [moving,      setMoving]        = useState(false)
  const [moveMsg,     setMoveMsg]       = useState(null)
  const { loadProject } = usePipeline()
  const navigate = useNavigate()
  const sd = project.script_data || {}
  const sections = sd.sections || {}

  const NODES = project.channel_template === 'zerourgency' ? [
    {key:'hook',label:'🎯 Hook'},{key:'context',label:'📖 Context & History'},
    {key:'deep_dive',label:'⚡ Deep Dive'},{key:'takeaway',label:'⚖️ Takeaway'},
  ] : [
    {key:'hook',label:'🎯 Hook'},{key:'thesis',label:'📖 Thesis'},{key:'bridge_ab',label:'🔗 Bridge A→B'},
    {key:'antithesis',label:'⚡ Antithesis'},{key:'bridge_bc',label:'🔗 Bridge B→C'},{key:'synthesis',label:'⚖️ Synthesis'},
  ]

  const handleMove = async (destination) => {
    setShowBrowser(false)
    setMoving(true); setMoveMsg(null)
    try {
      const r = await axios.post(`/api/projects/${project.id}/move`, { destination })
      setMoveMsg({ type:'success', text: `✅ Moved to: ${r.data.new_path}` })
      onMoved && onMoved(project.id, r.data.new_path)
    } catch(e) {
      setMoveMsg({ type:'error', text: `❌ ${e.response?.data?.detail || e}` })
    }
    setMoving(false)
  }

  const openInGenerator = () => {
    loadProject(project)
    navigate(`/projects/${project.id}`)
  }

  return (
    <>
      {showBrowser && <FolderBrowser onSelect={handleMove} onClose={() => setShowBrowser(false)} />}

      <div style={{position:'fixed',inset:0,background:'rgba(0,0,0,0.75)',display:'flex',alignItems:'center',justifyContent:'center',zIndex:1000}} onClick={onClose}>
        <div style={{background:'var(--bg-card)',border:'1px solid var(--border)',borderRadius:'var(--radius)',width:680,maxWidth:'92vw',maxHeight:'85vh',display:'flex',flexDirection:'column'}} onClick={e=>e.stopPropagation()}>

          {/* Header */}
          <div style={{display:'flex',alignItems:'flex-start',gap:12,padding:'18px 20px',borderBottom:'1px solid var(--border)'}}>
            <div style={{flex:1}}>
              <div style={{marginBottom:8}}><PhaseBadge phase={project.phase}/></div>
              <h3 style={{fontSize:17,fontWeight:600,lineHeight:1.4}}>{project.topic}</h3>
              <div style={{fontSize:12,color:'var(--text-muted)',marginTop:4}}>
                {sd.word_count && <span>{sd.word_count} words · </span>}
                Created {project.created_at?.slice(0,10)} · Updated {project.updated_at?.slice(0,10)}
              </div>
            </div>
            <button className="btn btn-ghost btn-sm" onClick={onClose} style={{padding:4,flexShrink:0}}><X size={16}/></button>
          </div>

          {/* Body */}
          <div style={{flex:1,overflowY:'auto',padding:'18px 20px',display:'flex',flexDirection:'column',gap:16}}>

            {/* YouTube link */}
            {project.yt_url && (
              <div className="alert alert-success" style={{margin:0}}>
                <Youtube size={14}/>
                <a href={project.yt_url} target="_blank" rel="noreferrer" style={{color:'var(--green)'}}>{project.yt_url}</a>
              </div>
            )}

            {/* Video */}
            {project.has_video && project.video_path && (
              <div>
                <div className="card-title">🎬 Video</div>
                <video controls style={{width:'100%',borderRadius:8}}
                  src={`/api/video-file/${encodeURIComponent(project.video_path)}`}/>
              </div>
            )}

            {/* Script sections */}
            {Object.values(sections).some(v => v) && (
              <details>
                <summary style={{cursor:'pointer',fontWeight:600,color:'var(--text-muted)',fontSize:13,marginBottom:10}}>📄 Script</summary>
                <div style={{display:'flex',flexDirection:'column',gap:12,marginTop:10}}>
                  {NODES.map(n => sections[n.key] ? (
                    <div key={n.key}>
                      <div className="node-label">{n.label}</div>
                      <div className="node-text" style={{fontSize:13}}>{sections[n.key]}</div>
                    </div>
                  ) : null)}
                </div>
              </details>
            )}

            {/* Folder path */}
            <div>
              <div className="card-title" style={{marginBottom:6}}>📁 Folder</div>
              <code style={{fontSize:12,color:'var(--text-muted)',background:'var(--bg-elevated)',padding:'6px 10px',borderRadius:6,display:'block',wordBreak:'break-all'}}>
                {project.folder_path}
              </code>
            </div>

            {/* Move result */}
            {moveMsg && (
              <div className={`alert alert-${moveMsg.type === 'success' ? 'success' : 'error'}`} style={{margin:0}}>
                {moveMsg.text}
              </div>
            )}
          </div>

          {/* Footer actions */}
          <div style={{display:'flex',gap:10,padding:'14px 20px',borderTop:'1px solid var(--border)',flexWrap:'wrap'}}>
            <button className="btn btn-secondary" disabled={moving} onClick={() => setShowBrowser(true)}>
              {moving ? <><Loader size={13} style={{animation:'spin 1s linear infinite'}}/> Moving…</> : <><Move size={13}/> Move Folder</>}
            </button>
            <div style={{flex:1}}/>
            {project.phase !== 'published' && (
              <button className="btn btn-primary" onClick={openInGenerator}>
                Continue <ChevronRight size={14}/>
              </button>
            )}
          </div>
        </div>
      </div>
    </>
  )
}

// ── New Project Modal ──────────────────────────────────────────
function NewProjectModal({ onClose, onCreate }) {
  const [topic, setTopic] = useState('')
  const [channelTemplate, setChannelTemplate] = useState('still_point')
  const [busy,  setBusy]  = useState(false)

  const submit = async () => {
    if (!topic.trim()) return
    setBusy(true)
    try {
      const r = await axios.post('/api/projects', { 
        topic: topic.trim(), 
        channel_template: channelTemplate 
      })
      onCreate(r.data)
    } catch(e) { console.error(e) }
    setBusy(false)
  }

  return (
    <div style={{position:'fixed',inset:0,background:'rgba(0,0,0,0.7)',display:'flex',alignItems:'center',justifyContent:'center',zIndex:1000}} onClick={onClose}>
      <div style={{background:'var(--bg-card)',border:'1px solid var(--border)',borderRadius:'var(--radius)',padding:28,width:480,maxWidth:'90vw'}} onClick={e=>e.stopPropagation()}>
        <h3 style={{fontFamily:'var(--font-serif)',fontSize:20,marginBottom:20}}>New Project</h3>
        <div className="input-group">
          <label>Topic / Thesis</label>
          <input type="text" value={topic} autoFocus onChange={e=>setTopic(e.target.value)}
            onKeyDown={e=>e.key==='Enter'&&submit()}
            placeholder="e.g. The commodification of human attention"/>
        </div>
        <div className="input-group">
          <label>Channel Format</label>
          <select value={channelTemplate} onChange={e=>setChannelTemplate(e.target.value)}>
            <option value="still_point">⚖️ Still Point (Dialectic)</option>
            <option value="zerourgency">📺 ZeroUrgency (Infotainment)</option>
          </select>
        </div>
        <div style={{display:'flex',gap:10,justifyContent:'flex-end',marginTop:20}}>
          <button className="btn btn-ghost" onClick={onClose}>Cancel</button>
          <button className="btn btn-primary" disabled={!topic.trim()||busy} onClick={submit}>
            {busy?'Creating…':'Create Project →'}
          </button>
        </div>
      </div>
    </div>
  )
}

// ── Project Card ───────────────────────────────────────────────
function ProjectCard({ project, onDelete, onOpen }) {
  return (
    <div className="card"
      style={{cursor:'pointer',transition:'border-color 0.2s,box-shadow 0.2s'}}
      onClick={() => onOpen(project)}
      onMouseEnter={e=>{e.currentTarget.style.borderColor='var(--accent)';e.currentTarget.style.boxShadow='0 0 0 1px var(--accent-glow)'}}
      onMouseLeave={e=>{e.currentTarget.style.borderColor='var(--border)';e.currentTarget.style.boxShadow='none'}}
    >
      <div style={{display:'flex',justifyContent:'space-between',alignItems:'flex-start',marginBottom:10}}>
        <PhaseBadge phase={project.phase}/>
        <button className="btn btn-danger btn-sm" style={{padding:'4px 8px'}}
          onClick={e=>{e.stopPropagation();onDelete(project.id)}}>
          <Trash2 size={12}/>
        </button>
      </div>

      <h3 style={{fontSize:15,fontWeight:600,lineHeight:1.4,marginBottom:8}}>{project.topic}</h3>

      <div style={{fontSize:12,color:'var(--text-muted)',marginBottom:12}}>
        {project.script_data?.word_count && <span>{project.script_data.word_count} words · </span>}
        {project.updated_at?.slice(0,10)}
      </div>

      {project.yt_url && (
        <a href={project.yt_url} target="_blank" rel="noreferrer"
          style={{fontSize:12,color:'#ff7070',display:'flex',alignItems:'center',gap:4,marginBottom:10}}
          onClick={e=>e.stopPropagation()}>
          <Youtube size={13}/> View on YouTube
        </a>
      )}

      <div style={{display:'flex',alignItems:'center',gap:6,color:'var(--accent)',fontSize:13,fontWeight:600}}>
        {project.phase==='published' ? 'View details' : 'Continue'} <ChevronRight size={13}/>
      </div>
    </div>
  )
}

// ── Projects Page ──────────────────────────────────────────────
export default function Projects() {
  const [projects,  setProjects]  = useState([])
  const [loading,   setLoading]   = useState(true)
  const [showModal, setShowModal] = useState(false)
  const [detail,    setDetail]    = useState(null)   // project being viewed
  const { loadProject } = usePipeline()
  const navigate = useNavigate()

  const load = async () => {
    setLoading(true)
    try { const r = await axios.get('/api/projects'); setProjects(r.data) }
    catch(_) {}
    setLoading(false)
  }

  useEffect(() => { load() }, [])

  const handleCreate = (project) => {
    setShowModal(false)
    loadProject(project)
    navigate(`/projects/${project.id}`)
  }

  const handleOpen = (project) => {
    // Published → show detail panel; others → open generator
    if (project.phase === 'published') {
      setDetail(project)
    } else {
      loadProject(project)
      navigate(`/projects/${project.id}`)
    }
  }

  const handleDelete = async (id) => {
    await axios.delete(`/api/projects/${id}`)
    setProjects(ps => ps.filter(p => p.id !== id))
    if (detail?.id === id) setDetail(null)
  }

  const handleMoved = (id, newPath) => {
    setProjects(ps => ps.map(p => p.id === id ? {...p, folder_path: newPath} : p))
    setDetail(prev => prev?.id === id ? {...prev, folder_path: newPath} : prev)
  }

  const groups = {
    drafting:    projects.filter(p => p.phase === 'drafting'),
    script_done: projects.filter(p => p.phase === 'script_done'),
    video_done:  projects.filter(p => p.phase === 'video_done'),
    published:   projects.filter(p => p.phase === 'published'),
  }

  return (
    <div>
      {showModal && <NewProjectModal onClose={()=>setShowModal(false)} onCreate={handleCreate}/>}
      {detail    && <ProjectDetail project={detail} onClose={()=>setDetail(null)} onMoved={handleMoved}/>}

      <div className="page-header" style={{display:'flex',justifyContent:'space-between',alignItems:'flex-end'}}>
        <div>
          <h2>Projects</h2>
          <p>Each video is a project — track it from script to YouTube.</p>
        </div>
        <button className="btn btn-primary" onClick={()=>setShowModal(true)}>
          <Plus size={15}/> New Project
        </button>
      </div>

      {loading ? (
        <p style={{color:'var(--text-muted)'}}>Loading projects…</p>
      ) : projects.length === 0 ? (
        <div className="alert alert-info" style={{marginTop:20}}>
          No projects yet. Click <strong>New Project</strong> to start your first video.
        </div>
      ) : (
        <>
          {[
            ['drafting',    '⚡ In Progress'],
            ['script_done', '📝 Script Ready'],
            ['video_done',  '🎬 Video Ready'],
            ['published',   '✅ Published'],
          ].map(([phase, label]) => groups[phase].length > 0 && (
            <div key={phase} style={{marginBottom:32}}>
              <div style={{display:'flex',alignItems:'center',gap:10,marginBottom:14,paddingBottom:8,borderBottom:'1px solid var(--border)'}}>
                <span style={{fontSize:14,fontWeight:600,color:'var(--text-muted)'}}>{label}</span>
                <span className="badge badge-muted">{groups[phase].length}</span>
              </div>
              <div style={{display:'grid',gridTemplateColumns:'repeat(auto-fill,minmax(280px,1fr))',gap:14}}>
                {groups[phase].map(p => (
                  <ProjectCard key={p.id} project={p} onOpen={handleOpen} onDelete={handleDelete}/>
                ))}
              </div>
            </div>
          ))}
        </>
      )}
    </div>
  )
}
