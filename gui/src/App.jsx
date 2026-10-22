import React, { useState } from 'react';
import { 
  Box, 
  Layers, 
  UploadCloud, 
  Info, 
  Cpu, 
  CheckCircle2, 
  Sliders, 
  FolderTree, 
  FileCode, 
  RefreshCw, 
  Camera, 
  Compass, 
  Eye, 
  Play
} from 'lucide-react';

export default function App() {
  const [activeTab, setActiveTab] = useState('pipeline');
  const [lodLevel, setLodLevel] = useState(300);
  const [denoiseMirror, setDenoiseMirror] = useState(true);
  const [navvisAutoUnify, setNavvisAutoUnify] = useState(true);
  const [selectedWalks, setSelectedWalks] = useState([
    { id: 'walk_01', path: 'dataset_walk_01', panos: 242, status: 'Registered' },
    { id: 'walk_02', path: 'dataset_walk_02', panos: 188, status: 'Registered' }
  ]);
  const [isProcessing, setIsProcessing] = useState(false);
  const [progress, setProgress] = useState(0);

  const startConversion = () => {
    setIsProcessing(true);
    setProgress(15);
    setTimeout(() => setProgress(45), 1000);
    setTimeout(() => setProgress(80), 2200);
    setTimeout(() => {
      setProgress(100);
      setIsProcessing(false);
    }, 3500);
  };

  return (
    <div className="flex h-screen w-screen overflow-hidden bg-[#0a0d14] text-slate-100 font-sans relative">
      {/* Background Ambient Glows */}
      <div className="absolute top-[-10%] left-[-10%] w-[500px] h-[500px] bg-blue-600/15 rounded-full blur-[140px] pointer-events-none" />
      <div className="absolute bottom-[-10%] right-[-10%] w-[600px] h-[600px] bg-purple-600/15 rounded-full blur-[160px] pointer-events-none" />
      <div className="absolute top-[40%] left-[30%] w-[400px] h-[400px] bg-cyan-500/10 rounded-full blur-[150px] pointer-events-none" />

      {/* Main Glass Workspace Shell */}
      <div className="flex flex-col flex-1 h-full z-10 p-4 gap-4">
        
        {/* Top Header Bar */}
        <header className="glass-panel rounded-2xl h-16 px-6 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-xl bg-gradient-to-tr from-blue-500 to-indigo-600 flex items-center justify-center shadow-lg shadow-blue-500/30">
              <Box className="w-5 h-5 text-white" />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <h1 className="font-semibold text-lg tracking-tight">reisource scan2bim</h1>
                <span className="text-xs px-2 py-0.5 rounded-full bg-blue-500/20 text-blue-300 border border-blue-400/30 font-medium">v1.2 AI</span>
              </div>
              <p className="text-xs text-slate-400">Automated High-LOD LiDAR & NavVis VLX to Native Revit / IFC Engine</p>
            </div>
          </div>

          <div className="flex items-center gap-3">
            <button 
              onClick={() => setActiveTab('pipeline')}
              className={`px-4 py-1.5 rounded-xl text-sm font-medium transition-all ${activeTab === 'pipeline' ? 'bg-white/15 text-white border border-white/20 shadow-sm' : 'text-slate-400 hover:text-slate-200'}`}
            >
              Pipeline & Ingestion
            </button>
            <button 
              onClick={() => setActiveTab('viewer')}
              className={`px-4 py-1.5 rounded-xl text-sm font-medium transition-all ${activeTab === 'viewer' ? 'bg-white/15 text-white border border-white/20 shadow-sm' : 'text-slate-400 hover:text-slate-200'}`}
            >
              Spatial 3D & Panos
            </button>
            <button 
              onClick={() => setActiveTab('export')}
              className={`px-4 py-1.5 rounded-xl text-sm font-medium transition-all ${activeTab === 'export' ? 'bg-white/15 text-white border border-white/20 shadow-sm' : 'text-slate-400 hover:text-slate-200'}`}
            >
              Revit / IFC Deliverables
            </button>

            <div className="h-5 w-[1px] bg-white/15 mx-1" />

            <a 
              href="https://github.com/callen0817/reisource_scan2bim" 
              target="_blank" 
              rel="noreferrer"
              className="glass-button px-3 py-1.5 rounded-xl text-slate-300 hover:text-white flex items-center gap-2 text-xs"
            >
              <FileCode className="w-3.5 h-3.5 text-blue-400" />
              <span>GitHub</span>
            </a>
          </div>
        </header>

        {/* Dynamic Content Body */}
        <div className="flex-1 flex gap-4 min-h-0">
          
          {/* Left Column: Input Data Ingestion & NavVis Bundle Disambiguator */}
          <div className="w-[420px] flex flex-col gap-4">
            
            {/* Drag & Drop Card */}
            <div className="glass-panel rounded-2xl p-5 flex flex-col gap-3 relative overflow-hidden group">
              <div className="flex items-center justify-between">
                <span className="text-xs font-semibold uppercase tracking-wider text-slate-400">Dataset Ingestion</span>
                
                {/* Hoverable Info Tooltip */}
                <div className="relative group/info">
                  <Info className="w-4 h-4 text-slate-400 hover:text-blue-400 cursor-pointer transition-colors" />
                  <div className="absolute right-0 top-6 w-80 p-3.5 glass-panel-elevated rounded-xl text-xs text-slate-200 shadow-2xl opacity-0 pointer-events-none group-hover/info:opacity-100 group-hover/info:pointer-events-auto transition-all z-50">
                    <p className="font-semibold text-white mb-1">What to drop here:</p>
                    <ul className="list-disc list-inside space-y-1 text-slate-300">
                      <li><strong className="text-blue-300">Point Cloud:</strong> Merged <code className="text-xs bg-white/10 px-1 py-0.5 rounded">.e57</code>, <code className="text-xs bg-white/10 px-1 py-0.5 rounded">.ply</code>, or <code className="text-xs bg-white/10 px-1 py-0.5 rounded">.laz</code></li>
                      <li><strong className="text-purple-300">NavVis VLX:</strong> Parent site folder containing <code className="text-xs bg-white/10 px-1 py-0.5 rounded">alignment.xml</code> and child walk folders with <code className="text-xs bg-white/10 px-1 py-0.5 rounded">poses.csv</code> & <code className="text-xs bg-white/10 px-1 py-0.5 rounded">pano/</code></li>
                      <li><strong className="text-emerald-300">No Renaming Needed:</strong> Microsecond UNIX timestamps and alignment matrices are unified in memory without modifying your raw files.</li>
                    </ul>
                  </div>
                </div>
              </div>

              {/* Upload Dropzone */}
              <div className="border border-dashed border-white/20 hover:border-blue-400/60 rounded-xl p-6 flex flex-col items-center justify-center gap-2 bg-white/[0.02] hover:bg-white/[0.05] transition-all cursor-pointer">
                <div className="w-12 h-12 rounded-full bg-blue-500/10 border border-blue-500/20 flex items-center justify-center text-blue-400">
                  <UploadCloud className="w-6 h-6" />
                </div>
                <p className="text-sm font-medium text-slate-200">Drag & Drop Scan Folders or Files</p>
                <p className="text-xs text-slate-400 text-center">Auto-detects multi-dataset NavVis walks, point clouds, and alignment metadata</p>
              </div>

              {/* Ingested Walks Disambiguation Preview */}
              <div className="flex flex-col gap-2 pt-1">
                <div className="flex items-center justify-between text-xs text-slate-400">
                  <span>Detected Multi-Dataset Walks:</span>
                  <span className="text-blue-400 font-medium">2 Walks Unified</span>
                </div>

                <div className="space-y-1.5">
                  {selectedWalks.map((w) => (
                    <div key={w.id} className="flex items-center justify-between p-2.5 rounded-lg bg-white/[0.04] border border-white/10 text-xs">
                      <div className="flex items-center gap-2">
                        <Camera className="w-3.5 h-3.5 text-blue-400" />
                        <div>
                          <p className="font-medium text-slate-200">{w.path}</p>
                          <p className="text-[10px] text-slate-400">{w.panos} 360° panos • poses.csv</p>
                        </div>
                      </div>
                      <span className="px-2 py-0.5 rounded-full bg-emerald-500/20 text-emerald-300 border border-emerald-500/30 text-[10px] font-medium">
                        {w.status}
                      </span>
                    </div>
                  ))}
                </div>
              </div>
            </div>

            {/* AI Engine & Conversion Config */}
            <div className="glass-panel rounded-2xl p-5 flex flex-col gap-4 flex-1">
              <span className="text-xs font-semibold uppercase tracking-wider text-slate-400">Conversion Parameters</span>

              {/* LOD Slider */}
              <div className="flex flex-col gap-2">
                <div className="flex justify-between items-center text-xs">
                  <span className="text-slate-300">Level of Development (LOD):</span>
                  <span className="font-semibold text-blue-400 bg-blue-500/10 px-2 py-0.5 rounded border border-blue-500/20">LOD {lodLevel}</span>
                </div>
                <input 
                  type="range" 
                  min="200" 
                  max="350" 
                  step="50" 
                  value={lodLevel} 
                  onChange={(e) => setLodLevel(Number(e.target.value))}
                  className="w-full accent-blue-500 h-1.5 bg-white/10 rounded-lg cursor-pointer"
                />
                <div className="flex justify-between text-[10px] text-slate-400">
                  <span>LOD 200 (Massing)</span>
                  <span>LOD 300 (Standard)</span>
                  <span>LOD 350 (Full MEP & Detail)</span>
                </div>
              </div>

              {/* Feature Toggles */}
              <div className="space-y-2 pt-2">
                <label className="flex items-center justify-between text-xs text-slate-300 cursor-pointer">
                  <span>Specular Mirror Phantom Stripping</span>
                  <input 
                    type="checkbox" 
                    checked={denoiseMirror} 
                    onChange={(e) => setDenoiseMirror(e.target.checked)}
                    className="accent-blue-500 rounded" 
                  />
                </label>

                <label className="flex items-center justify-between text-xs text-slate-300 cursor-pointer">
                  <span>Relative NavVis Namespace Ingestion</span>
                  <input 
                    type="checkbox" 
                    checked={navvisAutoUnify} 
                    onChange={(e) => setNavvisAutoUnify(e.target.checked)}
                    className="accent-blue-500 rounded" 
                  />
                </label>

                <label className="flex items-center justify-between text-xs text-slate-300 cursor-pointer">
                  <span>Strict BIM Taxonomy (Ceiling / Floor / Awning)</span>
                  <input type="checkbox" defaultChecked className="accent-blue-500 rounded" />
                </label>

                <label className="flex items-center justify-between text-xs text-slate-300 cursor-pointer">
                  <span>Parametric Fixtures (No Boxy Placeholders)</span>
                  <input type="checkbox" defaultChecked className="accent-blue-500 rounded" />
                </label>
              </div>

              {/* Launch Action Button */}
              <div className="mt-auto pt-4">
                <button 
                  onClick={startConversion}
                  disabled={isProcessing}
                  className="w-full py-3 rounded-xl glass-button-primary font-medium text-sm flex items-center justify-center gap-2 cursor-pointer disabled:opacity-50"
                >
                  {isProcessing ? (
                    <>
                      <RefreshCw className="w-4 h-4 animate-spin" />
                      <span>Converting Scan to BIM ({progress}%)...</span>
                    </>
                  ) : (
                    <>
                      <Play className="w-4 h-4 fill-current" />
                      <span>Run Agentic Scan-to-BIM Conversion</span>
                    </>
                  )}
                </button>
              </div>
            </div>
          </div>

          {/* Right Column: 3D Visualizer & Pipeline Feed */}
          <div className="flex-1 flex flex-col gap-4">
            
            {/* 3D Viewport Card */}
            <div className="glass-panel rounded-2xl flex-1 relative overflow-hidden flex flex-col">
              {/* Overlay Viewport Controls */}
              <div className="absolute top-4 left-4 z-20 flex items-center gap-2">
                <span className="glass-panel px-3 py-1 rounded-lg text-xs font-medium text-slate-200 flex items-center gap-2">
                  <Compass className="w-3.5 h-3.5 text-blue-400" />
                  Eyes on Park • Retail & Clinical Model
                </span>
                <span className="glass-panel px-2.5 py-1 rounded-lg text-xs text-slate-300">18.26M Points Ingested</span>
              </div>

              <div className="absolute top-4 right-4 z-20 flex items-center gap-2">
                <button className="glass-button px-2.5 py-1 rounded-lg text-xs text-slate-300 flex items-center gap-1.5">
                  <Layers className="w-3.5 h-3.5 text-purple-400" />
                  <span>Collections</span>
                </button>
                <button className="glass-button px-2.5 py-1 rounded-lg text-xs text-slate-300 flex items-center gap-1.5">
                  <Eye className="w-3.5 h-3.5 text-emerald-400" />
                  <span>Point Cloud Overlay</span>
                </button>
              </div>

              {/* Interactive Visual Canvas / 3D Scene Mockup */}
              <div className="flex-1 relative bg-gradient-to-b from-[#0c1220] to-[#080b12] flex items-center justify-center">
                <div className="absolute inset-0 opacity-20 bg-[radial-gradient(#3b82f6_1px,transparent_1px)] [background-size:24px_24px]" />
                
                {/* 3D Geometric Preview Representation */}
                <div className="relative z-10 flex flex-col items-center gap-3">
                  <div className="w-64 h-44 rounded-2xl border border-white/20 bg-white/[0.04] backdrop-blur-md p-4 flex flex-col justify-between shadow-2xl">
                    <div className="flex justify-between items-start">
                      <div className="flex items-center gap-1.5 text-xs text-blue-300 font-medium">
                        <CheckCircle2 className="w-3.5 h-3.5" />
                        <span>High-LOD Architectural BIM</span>
                      </div>
                      <span className="text-[10px] text-slate-400">16 Walls • STC50</span>
                    </div>

                    <div className="grid grid-cols-2 gap-2 text-[11px] text-slate-300">
                      <div className="p-2 rounded bg-white/5 border border-white/10">
                        <p className="text-slate-400 text-[10px]">Plumbing</p>
                        <p className="font-semibold text-white">Flushometer Toilets</p>
                      </div>
                      <div className="p-2 rounded bg-white/5 border border-white/10">
                        <p className="text-slate-400 text-[10px]">Millwork</p>
                        <p className="font-semibold text-white">L-Shaped Oak Desk</p>
                      </div>
                    </div>

                    <div className="flex justify-between text-[10px] text-slate-400 pt-1 border-t border-white/10">
                      <span>Awning & ADA Ramp Run</span>
                      <span className="text-emerald-400">1:12 ADA Standard</span>
                    </div>
                  </div>

                  <p className="text-xs text-slate-400">Live synchronized with Blender 5.2 & Native Revit API</p>
                </div>
              </div>

              {/* Bottom Pipeline Progress / Log Feed */}
              <div className="h-28 glass-panel-elevated border-t border-white/10 px-5 py-3 flex flex-col justify-between">
                <div className="flex items-center justify-between text-xs">
                  <div className="flex items-center gap-2">
                    <span className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse" />
                    <span className="font-medium text-slate-200">BIM Conversion Engine Status: Ready</span>
                  </div>
                  <span className="text-slate-400">Output: IFC4 + Native Revit 2027 + Blender 5.2</span>
                </div>

                <div className="font-mono text-[11px] text-slate-400 truncate">
                  [SUCCESS] Multi-walk NavVis VLX unifier mapped 430 panos to global space. Mirror reflections eliminated. Standardized IFC4 swept solids instantiated.
                </div>

                <div className="w-full bg-white/10 h-1.5 rounded-full overflow-hidden">
                  <div 
                    className="bg-gradient-to-r from-blue-500 to-purple-500 h-full transition-all duration-300"
                    style={{ width: `${progress}%` }}
                  />
                </div>
              </div>
            </div>

          </div>

        </div>

      </div>
    </div>
  );
}
