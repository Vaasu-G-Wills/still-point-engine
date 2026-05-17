import { create } from 'zustand'

const usePipeline = create((set) => ({
  // ── Active project ────────────────────────────────────────────
  projectId:    null,
  setProjectId: (id) => set({ projectId: id }),

  // ── Generator state ──────────────────────────────────────────
  topic:        '',
  setTopic:     (t) => set({ topic: t }),

  phase:        1,
  setPhase:     (p) => set({ phase: p }),

  outputData:   null,
  setOutputData:(d) => set({ outputData: d }),

  ttsVoice:     '',
  setTtsVoice:  (v) => set({ ttsVoice: v }),

  wordByWord:   true,
  setWordByWord:(v) => set({ wordByWord: v }),

  subtitleMode: 'chunk',
  setSubtitleMode:(v) => set({ subtitleMode: v }),

  channelTemplate: 'still_point',
  setChannelTemplate:(v) => set({ channelTemplate: v }),

  // ── Generation log ───────────────────────────────────────────
  logLines:     [],
  addLog:       (line) => set((s) => ({ logLines: [...s.logLines, line] })),
  clearLog:     () => set({ logLines: [] }),

  // ── Streamed node text ───────────────────────────────────────
  nodes: {},
  setNode:    (key, text) => set((s) => ({ nodes: { ...s.nodes, [key]: text } })),
  clearNodes: () => set({ nodes: {} }),

  // ── YT metadata ──────────────────────────────────────────────
  ytMeta:    null,
  setYtMeta: (m) => set({ ytMeta: m }),

  ytResult:    null,
  setYtResult: (r) => set({ ytResult: r }),

  // ── Full reset for new project ────────────────────────────────
  resetForNew: () => set({
    projectId: null, phase: 1, outputData: null,
    logLines: [], ytMeta: null, ytResult: null,
    nodes: {},
  }),

  // ── Load existing project into store ─────────────────────────
  loadProject: (project) => set({
    projectId:  project.id,
    topic:      project.topic,
    channelTemplate: project.channel_template || 'still_point',
    outputData: project.script_data
      ? { ...project.script_data, folder_path: project.folder_path }
      : null,
    // Resume at correct phase
    phase: project.phase === 'drafting'     ? 1
         : project.phase === 'script_done'  ? 2
         : project.phase === 'video_done'   ? 3
         : project.phase === 'published'    ? 3
         : 1,
    ytResult: project.yt_url
      ? { url: project.yt_url, video_id: project.yt_video_id, privacy: 'public' }
      : null,
    logLines: [], ytMeta: null,
    nodes: {},
  }),
}))

export default usePipeline
