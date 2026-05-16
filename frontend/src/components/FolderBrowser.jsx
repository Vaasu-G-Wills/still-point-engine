import { useState, useEffect } from 'react'
import { FolderOpen, ArrowLeft, X, HardDrive, Home, Monitor } from 'lucide-react'
import axios from 'axios'

// Quick-access bookmarks — covers all drives on a typical Linux setup
const BOOKMARKS = [
  { label: '/ (Root)',       path: '/',             icon: <Monitor size={13}/> },
  { label: '~ (Home)',       path: '~',             icon: <Home size={13}/> },
  { label: '/media',         path: '/media',        icon: <HardDrive size={13}/> },
  { label: '/mnt',           path: '/mnt',          icon: <HardDrive size={13}/> },
  { label: '/run/media',     path: '/run/media',    icon: <HardDrive size={13}/> },
]

export default function FolderBrowser({ onSelect, onClose }) {
  const [path,    setPath]    = useState('/')
  const [entries, setEntries] = useState([])
  const [parent,  setParent]  = useState(null)
  const [loading, setLoading] = useState(false)
  const [error,   setError]   = useState(null)

  const nav = async (p) => {
    setLoading(true); setError(null)
    try {
      const r = await axios.get('/api/browse', { params: { path: p } })
      setPath(r.data.current)
      setEntries(r.data.entries)
      setParent(r.data.parent)
    } catch(e) {
      setError(e.response?.data?.detail || String(e))
    }
    setLoading(false)
  }

  // Start at filesystem root so all drives are visible
  useEffect(() => { nav('/') }, [])

  return (
    <div
      style={{position:'fixed',inset:0,background:'rgba(0,0,0,0.78)',display:'flex',alignItems:'center',justifyContent:'center',zIndex:2000}}
      onClick={onClose}
    >
      <div
        style={{background:'var(--bg-card)',border:'1px solid var(--border)',borderRadius:'var(--radius)',width:600,maxWidth:'92vw',maxHeight:'72vh',display:'flex',flexDirection:'column'}}
        onClick={e => e.stopPropagation()}
      >
        {/* Header */}
        <div style={{display:'flex',alignItems:'center',gap:10,padding:'14px 18px',borderBottom:'1px solid var(--border)'}}>
          <FolderOpen size={15} color="var(--accent)"/>
          <span style={{fontWeight:600,fontSize:14,flex:1}}>Select Destination Folder</span>
          <button className="btn btn-ghost btn-sm" onClick={onClose} style={{padding:4}}><X size={14}/></button>
        </div>

        {/* Current path breadcrumb */}
        <div style={{padding:'5px 18px',background:'var(--bg-elevated)',borderBottom:'1px solid var(--border)',fontSize:11,color:'var(--text-muted)',fontFamily:'monospace',wordBreak:'break-all'}}>
          {path}
        </div>

        <div style={{display:'flex',flex:1,overflow:'hidden'}}>

          {/* ── Bookmarks sidebar ── */}
          <div style={{width:150,flexShrink:0,borderRight:'1px solid var(--border)',padding:'8px 0',overflowY:'auto',background:'var(--bg-elevated)'}}>
            <div style={{padding:'4px 12px 8px',fontSize:10,fontWeight:700,textTransform:'uppercase',letterSpacing:'0.08em',color:'var(--text-subtle)'}}>
              Quick Access
            </div>
            {BOOKMARKS.map(b => (
              <div
                key={b.path}
                title={b.path}
                style={{display:'flex',alignItems:'center',gap:8,padding:'8px 12px',cursor:'pointer',fontSize:12,color:path===b.path?'var(--accent)':'var(--text-muted)',background:path===b.path?'var(--accent-glow)':'transparent',transition:'all 0.1s'}}
                onMouseEnter={e => { if (path!==b.path) e.currentTarget.style.background='rgba(255,255,255,0.04)' }}
                onMouseLeave={e => { if (path!==b.path) e.currentTarget.style.background='transparent' }}
                onClick={() => nav(b.path)}
              >
                {b.icon}
                <span style={{overflow:'hidden',textOverflow:'ellipsis',whiteSpace:'nowrap'}}>{b.label}</span>
              </div>
            ))}
          </div>

          {/* ── Directory listing ── */}
          <div style={{flex:1,overflowY:'auto',padding:'6px 0'}}>
            {loading && (
              <div style={{padding:24,textAlign:'center',color:'var(--text-muted)',fontSize:13}}>Loading…</div>
            )}
            {error && (
              <div style={{padding:'10px 18px',color:'var(--red)',fontSize:13}}>{error}</div>
            )}

            {/* Up / parent */}
            {parent && !loading && (
              <div
                style={{display:'flex',alignItems:'center',gap:10,padding:'9px 16px',cursor:'pointer',color:'var(--text-muted)',fontSize:13}}
                onMouseEnter={e => e.currentTarget.style.background='var(--bg-elevated)'}
                onMouseLeave={e => e.currentTarget.style.background='transparent'}
                onClick={() => nav(parent)}
              >
                <ArrowLeft size={13}/> ..
              </div>
            )}

            {!loading && entries.map(e => (
              <div
                key={e.path}
                style={{display:'flex',alignItems:'center',gap:10,padding:'9px 16px',cursor:'pointer',fontSize:13,color:'var(--text-primary)'}}
                onMouseEnter={el => el.currentTarget.style.background='var(--bg-elevated)'}
                onMouseLeave={el => el.currentTarget.style.background='transparent'}
                onClick={() => nav(e.path)}
              >
                <FolderOpen size={13} color="var(--accent)"/> {e.name}
              </div>
            ))}

            {!loading && entries.length === 0 && !error && (
              <div style={{padding:24,textAlign:'center',color:'var(--text-subtle)',fontSize:13}}>Empty folder</div>
            )}
          </div>
        </div>

        {/* Footer */}
        <div style={{display:'flex',gap:10,padding:'12px 18px',borderTop:'1px solid var(--border)',justifyContent:'space-between',alignItems:'center'}}>
          <span style={{fontSize:12,color:'var(--text-muted)',fontFamily:'monospace',flex:1,overflow:'hidden',textOverflow:'ellipsis',whiteSpace:'nowrap'}}>
            Selected: {path}
          </span>
          <div style={{display:'flex',gap:8,flexShrink:0}}>
            <button className="btn btn-ghost" onClick={onClose}>Cancel</button>
            <button className="btn btn-primary" onClick={() => onSelect(path)}>
              Use This Folder
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}
