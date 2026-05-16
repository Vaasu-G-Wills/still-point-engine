import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { RefreshCw, Zap } from 'lucide-react'
import usePipeline from '../store/pipeline'
import axios from 'axios'

const REGIONS = [
  {label:'🇮🇳 India (IN)', code:'IN'},
  {label:'🇺🇸 United States (US)', code:'US'},
  {label:'🇬🇧 United Kingdom (GB)', code:'GB'},
  {label:'🇦🇺 Australia (AU)', code:'AU'},
  {label:'🇨🇦 Canada (CA)', code:'CA'},
]

export default function Trends() {
  const [region,    setRegion]    = useState('IN')
  const [nTopics,   setNTopics]   = useState(8)
  const [busy,      setBusy]      = useState(false)
  const [creating,  setCreating]  = useState(null)  // topic string being created
  const [error,     setError]     = useState(null)
  const [result,    setResult]    = useState(null)
  const { loadProject } = usePipeline()
  const navigate = useNavigate()

  const fetchTrends = async () => {
    setBusy(true); setError(null); setResult(null)
    try {
      const r = await axios.post('/api/trends', {region_code: region, n_suggestions: nTopics})
      if (r.data.error) setError(r.data.error)
      else setResult(r.data)
    } catch(e) { setError(String(e)) }
    setBusy(false)
  }

  // Create a project then navigate into it
  const useTopic = async (topic) => {
    setCreating(topic)
    try {
      const r = await axios.post('/api/projects', { topic })
      loadProject(r.data)
      navigate(`/projects/${r.data.id}`)
    } catch(e) {
      setError(`Failed to create project: ${e}`)
    }
    setCreating(null)
  }

  return (
    <div>
      <div className="page-header">
        <h2>Trending Topics</h2>
        <p>Today's YouTube trends → philosophical dialectic angles via local LLM</p>
      </div>

      <div className="card" style={{marginBottom:20}}>
        <div className="row" style={{alignItems:'flex-end',gap:14}}>
          <div className="input-group" style={{flex:2,marginBottom:0}}>
            <label>Region</label>
            <select value={region} onChange={e=>setRegion(e.target.value)}>
              {REGIONS.map(r=><option key={r.code} value={r.code}>{r.label}</option>)}
            </select>
          </div>
          <div className="input-group" style={{flex:1,marginBottom:0}}>
            <label>Topics to suggest</label>
            <select value={nTopics} onChange={e=>setNTopics(Number(e.target.value))}>
              {[4,6,8,10,12].map(n=><option key={n} value={n}>{n}</option>)}
            </select>
          </div>
          <button className="btn btn-primary" disabled={busy} onClick={fetchTrends} style={{paddingTop:10,paddingBottom:10}}>
            {busy ? <><RefreshCw size={14} style={{animation:'spin 1s linear infinite'}}/> Fetching…</> : '🔄 Fetch Trends'}
          </button>
        </div>
      </div>

      {error && <div className="alert alert-error">{error}</div>}

      {result && (
        <>
          <p style={{fontSize:13,color:'var(--text-muted)',marginBottom:16}}>
            📊 Analysed <strong>{result.raw_video_count}</strong> trending videos · Region: <strong>{result.region}</strong> · {result.topics.length} topics extracted
          </p>
          <div className="trend-grid">
            {result.topics.map((t,i) => (
              <div key={i} className="trend-card">
                <h3>{t.topic}</h3>
                <span className="badge badge-muted" style={{width:'fit-content'}}>{t.category}</span>
                {t.rationale && <p>{t.rationale}</p>}
                <button
                  className="btn btn-secondary btn-sm"
                  style={{width:'100%', justifyContent:'center'}}
                  disabled={creating === t.topic}
                  onClick={() => useTopic(t.topic)}
                >
                  {creating === t.topic
                    ? <><RefreshCw size={13} style={{animation:'spin 1s linear infinite'}}/> Creating project…</>
                    : <><Zap size={13}/> Create project &amp; generate</>}
                </button>
              </div>
            ))}
          </div>
        </>
      )}
    </div>
  )
}
