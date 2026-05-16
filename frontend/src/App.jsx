import { BrowserRouter, Routes, Route, NavLink, Navigate } from 'react-router-dom'
import { LayoutGrid, BookOpen, TrendingUp } from 'lucide-react'
import Projects  from './pages/Projects'
import Generator from './pages/Generator'
import Library   from './pages/Library'
import Trends    from './pages/Trends'

export default function App() {
  return (
    <BrowserRouter>
      <div className="layout">
        <aside className="sidebar">
          <div className="sidebar-logo">
            <h1>Still Point<br /><span>Engine</span></h1>
            <p>Dialectic Script Pipeline</p>
          </div>
          <nav className="sidebar-nav">
            <NavLink to="/projects"
              className={({isActive}) => 'nav-item' + (isActive ? ' active' : '')}>
              <LayoutGrid size={16} /> Projects
            </NavLink>
            <NavLink to="/library"
              className={({isActive}) => 'nav-item' + (isActive ? ' active' : '')}>
              <BookOpen size={16} /> Library
            </NavLink>
            <NavLink to="/trends"
              className={({isActive}) => 'nav-item' + (isActive ? ' active' : '')}>
              <TrendingUp size={16} /> Trending
            </NavLink>
          </nav>
        </aside>

        <main className="main-content">
          <Routes>
            <Route path="/"               element={<Navigate to="/projects" replace />} />
            <Route path="/projects"       element={<Projects />} />
            <Route path="/projects/:id"   element={<Generator />} />
            <Route path="/library"        element={<Library />} />
            <Route path="/trends"         element={<Trends />} />
          </Routes>
        </main>
      </div>
    </BrowserRouter>
  )
}
