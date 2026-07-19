import { useEffect, useState } from 'react';
import { ChatInterface } from '../components/ChatInterface';
import { api, type Session } from '../api';
import { Navigation, Calendar, Mic, Car, ShoppingBag, Loader2 } from 'lucide-react';
import { useChat } from '../hooks/useChat';

const NODE_COORDS: Record<string, { x: number, y: number }> = {
  Gate_1: { x: 100, y: 150 },
  Gate_2: { x: 300, y: 150 },
  Gate_3: { x: 200, y: 250 },
  Concourse_N: { x: 200, y: 70 },
  Concourse_S: { x: 200, y: 230 },
  Section_A: { x: 130, y: 100 },
  Section_B: { x: 270, y: 100 },
  Section_C: { x: 130, y: 200 },
  Section_D: { x: 270, y: 200 },
  Restroom_1: { x: 150, y: 150 },
  Restroom_2: { x: 250, y: 150 },
  Food_Court: { x: 200, y: 150 },
  Medical_1: { x: 100, y: 70 },
  Security_HQ: { x: 300, y: 230 },
};

export function FanDashboard() {
  const [session, setSession] = useState<Session | null>(null);
  const { messages, sendMessage, isLoading } = useChat(session?.session_id || null);
  
  const [selectedZone, setSelectedZone] = useState<string | null>(null);
  const [densityStr, setDensityStr] = useState<string | null>(null);

  const handleZoneClick = async (zoneId: string) => {
    setSelectedZone(zoneId);
    setDensityStr("Loading...");
    try {
      const data = await api.getCrowdStatus();
      const zoneInfo = data.zones.find((z: any) => z.zone_id === zoneId);
      if (zoneInfo) {
        setDensityStr(`${Math.round(zoneInfo.occupancy_pct)}%`);
      } else {
        setDensityStr("N/A");
      }
    } catch (e) {
      setDensityStr("Error");
    }
  };

  const latestPathMsg = [...messages].reverse().find(m => m.data?.path);
  const activePath = latestPathMsg?.data?.path as string[] | undefined;

  useEffect(() => {
    // Initialize a Fan session
    api.createSession({
      role: 'fan',
      language: 'en',
      accessibility_needs: ['none'],
      ticket_zone: 'Gate_1'
    }).then(setSession);
  }, []);

  return (
    <div className="flex h-full min-h-0 w-full">
      {/* Left Panel: Map/Context */}
      <div className="w-2/3 p-6 flex flex-col gap-6 overflow-y-auto min-h-0">
        <div className="bg-fifa-grass text-white p-8 rounded-2xl shadow-sm relative overflow-hidden">
          <div className="relative z-10">
            <h1 className="text-3xl font-bold mb-2">Welcome to FIFA World Cup 26™</h1>
            <p className="text-grass-100 text-lg max-w-xl">
              Your digital stadium companion. Ask OffsideOperations for directions, wait times, or transport options.
            </p>
          </div>
          {/* Decorative element */}
          <div className="absolute -bottom-24 -right-24 w-64 h-64 bg-white opacity-10 rounded-full blur-2xl"></div>
        </div>

        <div className="grid grid-cols-2 gap-4">
          {/* Live Scorecard & Commentary Card */}
          <div className="card p-5 bg-gradient-to-br from-gray-900 to-gray-800 border-gray-700 col-span-2 md:col-span-1">
            <div className="flex items-center gap-3 mb-3 text-fifa-grass font-semibold">
              <Calendar size={20} />
              <h3>Match Center</h3>
            </div>
            <div className="text-center py-2">
              <div className="flex justify-between items-center px-4 mb-2">
                <div className="font-bold text-xl text-white">USA</div>
                <div className="font-bold text-2xl text-fifa-grass">2 - 1</div>
                <div className="font-bold text-xl text-white">BRA</div>
              </div>
              <div className="text-xs text-red-400 font-bold animate-pulse">75' LIVE</div>
            </div>
            <button disabled={isLoading} className="w-full mt-3 bg-blue-600 hover:bg-blue-700 disabled:opacity-50 text-white font-medium py-2 rounded transition-colors flex items-center justify-center gap-2">
              {isLoading ? <Loader2 size={16} className="animate-spin" /> : <Mic size={16} />}
              <span>Listen to Live Commentary</span>
            </button>
          </div>

          {/* Transport & Parking */}
          <div className="card p-5 col-span-2 md:col-span-1">
            <div className="flex items-center gap-3 mb-3 text-blue-400 font-semibold">
              <Car size={20} />
              <h3>Transport & Parking</h3>
            </div>
            <div className="flex flex-col gap-2">
              <button disabled={isLoading} onClick={() => sendMessage("Where is my vehicle pickup zone?")} className="text-left text-sm text-gray-300 bg-gray-800 hover:bg-gray-700 p-2 rounded transition-colors group flex justify-between disabled:opacity-50">
                <span>"Where is my vehicle pickup zone?"</span>
                {isLoading ? <Loader2 size={16} className="animate-spin" /> : <span className="opacity-0 group-hover:opacity-100 transition-opacity">→</span>}
              </button>
              <button disabled={isLoading} onClick={() => sendMessage("What are the current traffic conditions?")} className="text-left text-sm text-gray-300 bg-gray-800 hover:bg-gray-700 p-2 rounded transition-colors group flex justify-between disabled:opacity-50">
                <span>"Check traffic conditions"</span>
                {isLoading ? <Loader2 size={16} className="animate-spin" /> : <span className="opacity-0 group-hover:opacity-100 transition-opacity">→</span>}
              </button>
              <button disabled={isLoading} onClick={() => sendMessage("I need to issue a parking ticket")} className="text-left text-sm text-gray-300 bg-gray-800 hover:bg-gray-700 p-2 rounded transition-colors group flex justify-between disabled:opacity-50">
                <span>"Issue a parking ticket"</span>
                {isLoading ? <Loader2 size={16} className="animate-spin" /> : <span className="opacity-0 group-hover:opacity-100 transition-opacity">→</span>}
              </button>
            </div>
          </div>

          {/* Navigation & Wait Times */}
          <div className="card p-5 col-span-2 md:col-span-1">
            <div className="flex items-center gap-3 mb-3 text-fifa-grass font-semibold">
              <Navigation size={20} />
              <h3>Navigation & Wait Times</h3>
            </div>
            <div className="flex flex-col gap-2">
              <button disabled={isLoading} onClick={() => sendMessage("How do I get to Section B?")} className="text-left text-sm text-gray-300 bg-gray-800 hover:bg-gray-700 p-2 rounded transition-colors group flex justify-between disabled:opacity-50">
                <span>"How do I get to Section B?"</span>
                {isLoading ? <Loader2 size={16} className="animate-spin" /> : <span className="opacity-0 group-hover:opacity-100 transition-opacity">→</span>}
              </button>
              <button disabled={isLoading} onClick={() => sendMessage("Where's the nearest restroom?")} className="text-left text-sm text-gray-300 bg-gray-800 hover:bg-gray-700 p-2 rounded transition-colors group flex justify-between disabled:opacity-50">
                <span>"Where's the nearest restroom?"</span>
                {isLoading ? <Loader2 size={16} className="animate-spin" /> : <span className="opacity-0 group-hover:opacity-100 transition-opacity">→</span>}
              </button>
            </div>
          </div>

          {/* Store & Concessions */}
          <div className="card p-5 col-span-2 md:col-span-1">
            <div className="flex items-center gap-3 mb-3 text-fifa-red font-semibold">
              <ShoppingBag size={20} />
              <h3>Store & Concessions</h3>
            </div>
            <div className="flex flex-col gap-2">
              <button disabled={isLoading} onClick={() => sendMessage("I want to buy a USA jersey")} className="text-left text-sm text-gray-300 bg-gray-800 hover:bg-gray-700 p-2 rounded transition-colors group flex justify-between disabled:opacity-50">
                <span>"Buy Team Jersey"</span>
                {isLoading ? <Loader2 size={16} className="animate-spin" /> : <span className="opacity-0 group-hover:opacity-100 transition-opacity">→</span>}
              </button>
              <button disabled={isLoading} onClick={() => sendMessage("Order snacks to my seat in Gate 1")} className="text-left text-sm text-gray-300 bg-gray-800 hover:bg-gray-700 p-2 rounded transition-colors group flex justify-between disabled:opacity-50">
                <span>"Order snacks to seat"</span>
                {isLoading ? <Loader2 size={16} className="animate-spin" /> : <span className="opacity-0 group-hover:opacity-100 transition-opacity">→</span>}
              </button>
            </div>
          </div>
        </div>
        
        {/* Stadium Map Area */}
        <div className="flex-1 card flex flex-col items-center justify-center p-8 bg-gray-900/50 min-h-[300px] border border-gray-800 relative">
          <svg viewBox="0 0 400 300" className="w-full h-full max-h-[300px] opacity-90" xmlns="http://www.w3.org/2000/svg">
            
            {/* Football Pitch */}
            <rect x="100" y="70" width="200" height="160" fill="#2d6a4f" stroke="#ffffff" strokeWidth="2" opacity="0.8" />
            <line x1="200" y1="70" x2="200" y2="230" stroke="#ffffff" strokeWidth="2" opacity="0.6" />
            <circle cx="200" cy="150" r="30" fill="none" stroke="#ffffff" strokeWidth="2" opacity="0.6" />
            <rect x="100" y="110" width="30" height="80" fill="none" stroke="#ffffff" strokeWidth="2" opacity="0.6" />
            <rect x="270" y="110" width="30" height="80" fill="none" stroke="#ffffff" strokeWidth="2" opacity="0.6" />
            
            {/* Interactive Stands */}
            {/* North Stand */}
            <g className="cursor-pointer hover:opacity-80 transition-opacity" onClick={() => handleZoneClick("Section_A")}>
              <path d="M 100 65 L 300 65 L 280 30 L 120 30 Z" fill={selectedZone === "Section_A" ? "#39FF14" : "#4b5563"} stroke="#374151" strokeWidth="1" />
              <text x="200" y="52" fill={selectedZone === "Section_A" ? "#000" : "#fff"} fontSize="12" fontWeight="bold" textAnchor="middle">North Stand</text>
              {selectedZone === "Section_A" && densityStr && (
                <g transform="translate(200, 20)">
                  <rect x="-25" y="-14" width="50" height="18" fill="#111827" rx="4" />
                  <text x="0" y="-2" fill="#39FF14" fontSize="10" fontWeight="bold" textAnchor="middle">{densityStr}</text>
                </g>
              )}
            </g>

            {/* South Stand */}
            <g className="cursor-pointer hover:opacity-80 transition-opacity" onClick={() => handleZoneClick("Section_D")}>
              <path d="M 100 235 L 300 235 L 280 270 L 120 270 Z" fill={selectedZone === "Section_D" ? "#39FF14" : "#4b5563"} stroke="#374151" strokeWidth="1" />
              <text x="200" y="258" fill={selectedZone === "Section_D" ? "#000" : "#fff"} fontSize="12" fontWeight="bold" textAnchor="middle">South Stand</text>
              {selectedZone === "Section_D" && densityStr && (
                <g transform="translate(200, 290)">
                  <rect x="-25" y="-14" width="50" height="18" fill="#111827" rx="4" />
                  <text x="0" y="-2" fill="#39FF14" fontSize="10" fontWeight="bold" textAnchor="middle">{densityStr}</text>
                </g>
              )}
            </g>

            {/* East Stand */}
            <g className="cursor-pointer hover:opacity-80 transition-opacity" onClick={() => handleZoneClick("Section_C")}>
              <path d="M 305 70 L 305 230 L 340 210 L 340 90 Z" fill={selectedZone === "Section_C" ? "#39FF14" : "#4b5563"} stroke="#374151" strokeWidth="1" />
              <text x="325" y="150" fill={selectedZone === "Section_C" ? "#000" : "#fff"} fontSize="12" fontWeight="bold" textAnchor="middle" transform="rotate(90, 325, 150)">East</text>
              {selectedZone === "Section_C" && densityStr && (
                <g transform="translate(365, 150)">
                  <rect x="-25" y="-14" width="50" height="18" fill="#111827" rx="4" />
                  <text x="0" y="-2" fill="#39FF14" fontSize="10" fontWeight="bold" textAnchor="middle">{densityStr}</text>
                </g>
              )}
            </g>

            {/* West Stand */}
            <g className="cursor-pointer hover:opacity-80 transition-opacity" onClick={() => handleZoneClick("Section_F")}>
              <path d="M 95 70 L 95 230 L 60 210 L 60 90 Z" fill={selectedZone === "Section_F" ? "#39FF14" : "#4b5563"} stroke="#374151" strokeWidth="1" />
              <text x="75" y="150" fill={selectedZone === "Section_F" ? "#000" : "#fff"} fontSize="12" fontWeight="bold" textAnchor="middle" transform="rotate(-90, 75, 150)">West</text>
              {selectedZone === "Section_F" && densityStr && (
                <g transform="translate(35, 150)">
                  <rect x="-25" y="-14" width="50" height="18" fill="#111827" rx="4" />
                  <text x="0" y="-2" fill="#39FF14" fontSize="10" fontWeight="bold" textAnchor="middle">{densityStr}</text>
                </g>
              )}
            </g>

            {/* Dynamic Path */}
            {activePath && activePath.length > 1 && (
              <>
                <path 
                  d={`M${activePath.map((p: string) => {
                    const c = NODE_COORDS[p] || { x: 200, y: 150 };
                    return `${c.x},${c.y}`;
                  }).join(' L')}`}
                  fill="none" 
                  stroke="#39FF14" 
                  strokeWidth="3" 
                  strokeDasharray="6,6"
                >
                  <animate attributeName="stroke-dashoffset" from="100" to="0" dur="2s" repeatCount="indefinite"/>
                </path>
                {activePath.map((p: string, i: number) => {
                  const c = NODE_COORDS[p] || { x: 200, y: 150 };
                  const isEnd = i === activePath.length - 1;
                  return (
                    <circle key={p} cx={c.x} cy={c.y} r={isEnd ? 8 : 4} fill={isEnd ? "#ff0055" : "#39FF14"} />
                  );
                })}
              </>
            )}

            {/* Aesthetic "You are here" marker in North Stand */}
            {!activePath && (
              <g transform={`translate(200, 48)`}>
                <circle cx="0" cy="0" r="16" fill="#39FF14" opacity="0.2">
                  <animate attributeName="r" values="12;24;12" dur="2s" repeatCount="indefinite" />
                  <animate attributeName="opacity" values="0.6;0;0.6" dur="2s" repeatCount="indefinite" />
                </circle>
                <circle cx="0" cy="0" r="8" fill="#39FF14">
                  <animate attributeName="opacity" values="0.8;1;0.8" dur="2s" repeatCount="indefinite" />
                </circle>
                <circle cx="0" cy="0" r="4" fill="#ffffff" />
                <rect x="-40" y="-32" width="80" height="18" rx="4" fill="#111827" stroke="#374151" strokeWidth="1" />
                <text x="0" y="-20" fontSize="10" fill="#39FF14" textAnchor="middle" fontWeight="bold">YOU ARE HERE</text>
              </g>
            )}
          </svg>
          <p className="text-xs text-gray-400 mt-4 text-center">
            Click any stand to view live crowd density. {activePath ? "OffsideOperations is guiding you." : ""}
          </p>
        </div>
      </div>

      {/* Right Panel: Chat Assistant */}
      <div className="w-1/3 border-l border-gray-800 bg-gray-900/30 p-4 flex flex-col min-h-0">
        <ChatInterface 
          sessionId={session?.session_id || null} 
          messages={messages}
          isLoading={isLoading}
          onSendMessage={sendMessage}
          placeholder="Ask for directions or help..."
        />
      </div>
    </div>
  );
}
