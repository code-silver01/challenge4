import { useEffect, useState, useRef } from 'react';
import { api, type Session } from '../api';
import { Users, AlertTriangle, Activity, Megaphone, Terminal, Loader2 } from 'lucide-react';

interface ActionLog {
  id: string;
  timestamp: Date;
  type: 'PA' | 'Dispatch' | 'System';
  message: string;
  data?: any;
}

export function OrganizerDashboard() {
  const [session, setSession] = useState<Session | null>(null);
  const [actionLogs, setActionLogs] = useState<ActionLog[]>([]);
  const [isExecuting, setIsExecuting] = useState(false);
  
  const [paSelection, setPaSelection] = useState("Draft an announcement that Gate 3 is temporarily closed");
  const [dispatchSelection, setDispatchSelection] = useState("We need someone for a spill at Concourse N");
  const logsEndRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    logsEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [actionLogs]);

  const executeAction = async (type: 'PA' | 'Dispatch', text: string) => {
    if (!session) return;
    setIsExecuting(true);
    
    // Optimistic log
    const logId = Math.random().toString(36).substr(2, 9);
    setActionLogs(prev => [...prev, {
      id: logId,
      timestamp: new Date(),
      type,
      message: `Executing: ${text}...`
    }]);

    try {
      const response = await api.sendMessage(session.session_id, text);
      setActionLogs(prev => prev.map(log => 
        log.id === logId 
          ? { ...log, message: response.response, data: response.data }
          : log
      ));
    } catch (error) {
      setActionLogs(prev => prev.map(log => 
        log.id === logId 
          ? { ...log, message: "Action failed due to an error." }
          : log
      ));
    } finally {
      setIsExecuting(false);
    }
  };
  const [crowdData, setCrowdData] = useState<any>(null);
  const [alerts, setAlerts] = useState<any[]>([]);

  useEffect(() => {
    api.createSession({
      role: 'organizer',
      language: 'en',
      accessibility_needs: ['none']
    }).then(setSession);
  }, []);

  useEffect(() => {
    if (!session) return;
    
    // Poll for live data every 10 seconds
    const fetchData = async () => {
      try {
        const crowd = await api.getCrowdStatus();
        setCrowdData(crowd);
        const wAlerts = await api.getWellbeingAlerts(session.session_id);
        setAlerts(wAlerts);
      } catch (e) {
        console.error(e);
      }
    };
    
    fetchData();
    const interval = setInterval(fetchData, 10000);
    return () => clearInterval(interval);
  }, [session]);

  return (
    <div className="flex h-full min-h-0 w-full bg-transparent">
      {/* Left Panel: Ops Dashboards */}
      <div className="w-2/3 p-6 flex flex-col gap-6 overflow-y-auto min-h-0">
        <div className="flex items-center justify-between">
          <h1 className="text-2xl font-bold text-gray-100">Operations Center</h1>
          <span className="px-3 py-1 bg-fifa-grass text-white text-xs font-bold rounded-full animate-pulse">
            LIVE SYSTEM
          </span>
        </div>

        {/* Crowd Matrix */}
        <div className="card p-5">
          <div className="flex items-center gap-2 mb-4">
            <Users className="text-fifa-grass" size={20} />
            <h2 className="font-semibold text-lg">Crowd Density (Live)</h2>
          </div>
          <div className="grid grid-cols-4 gap-4 max-h-64 overflow-y-auto pr-2 custom-scrollbar">
            {crowdData?.zones?.map((zone: any) => (
              <div key={zone.zone_id} className={`p-3 rounded-lg border ${
                zone.occupancy_pct > 80 ? 'bg-red-900/30 border-red-800' :
                zone.occupancy_pct > 60 ? 'bg-orange-900/30 border-orange-800' :
                'bg-gray-800 border-gray-700'
              }`}>
                <div className="text-sm font-medium text-gray-400 mb-1 truncate" title={zone.zone_name}>{zone.zone_name}</div>
                <div className={`text-2xl font-bold ${
                  zone.occupancy_pct > 80 ? 'text-fifa-red' : 'text-gray-100'
                }`}>
                  {zone.occupancy_pct.toFixed(0)}%
                </div>
              </div>
            ))}
            {!crowdData && <div className="col-span-4 text-center text-sm text-gray-400 py-4">Loading crowd data...</div>}
          </div>
        </div>

        {/* Wellbeing Alerts */}
        <div className="card p-5">
          <div className="flex items-center gap-2 mb-4">
            <Activity className="text-fifa-red" size={20} />
            <h2 className="font-semibold text-lg">Volunteer Wellbeing Alerts</h2>
          </div>
          <div className="max-h-64 overflow-y-auto pr-2 custom-scrollbar">
            {alerts.length === 0 ? (
              <div className="text-sm text-gray-400 bg-gray-800 p-3 rounded-lg border border-gray-700">All volunteers operating within healthy limits.</div>
            ) : (
              <div className="space-y-3">
                {alerts.map((a: any, i) => (
                  <div key={i} className="flex gap-3 items-start p-3 bg-red-900/30 text-red-200 rounded-lg border border-red-800">
                    <AlertTriangle size={18} className="mt-0.5 text-fifa-red flex-shrink-0" />
                    <div>
                      <div className="font-semibold text-sm">{a.volunteer_name} (Shift: {a.shift_duration_hours.toFixed(1)}h)</div>
                      <div className="text-sm mt-1">{a.nudge_message}</div>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>

        {/* Quick Actions */}
        <div className="grid grid-cols-2 gap-4">
          <div className="card p-5 bg-gradient-to-br from-gray-900 to-gray-800 text-white flex flex-col h-full">
            <div className="flex items-center gap-2 mb-2">
              <Megaphone size={18} className="text-gray-300" />
              <h3 className="font-semibold">PA Announcements</h3>
            </div>
            <p className="text-xs text-gray-400 mb-4 flex-1">Broadcast automated multilingual messages across the stadium system.</p>
            
            <div className="flex flex-col gap-2 mt-auto">
              <select 
                value={paSelection}
                onChange={e => setPaSelection(e.target.value)}
                className="w-full bg-gray-800 border border-gray-700 text-sm text-white rounded p-2 focus:ring-1 focus:ring-fifa-grass outline-none"
              >
                <option value="Draft an announcement that Gate 3 is temporarily closed">Gate 3 temporarily closed</option>
                <option value="Draft an announcement that the match is delayed by 15 mins">Match delayed by 15 mins</option>
                <option value="Draft an announcement for a lost child at the Info Desk">Lost child at Info Desk</option>
              </select>
              <button 
                disabled={isExecuting}
                onClick={() => executeAction('PA', paSelection)}
                className="w-full bg-gray-700 hover:bg-gray-600 text-white font-medium py-2 rounded transition-colors disabled:opacity-50 flex items-center justify-center gap-2"
              >
                {isExecuting ? <Loader2 size={16} className="animate-spin" /> : <span>Execute Broadcast</span>}
              </button>
            </div>
          </div>
          
          <div className="card p-5 bg-gradient-to-br from-fifa-grass to-green-800 text-white flex flex-col h-full">
            <div className="flex items-center gap-2 mb-2">
              <Users size={18} className="text-green-200" />
              <h3 className="font-semibold">Smart Dispatch</h3>
            </div>
            <p className="text-xs text-green-100 mb-4 flex-1">Find and dispatch the optimal available volunteer for incidents.</p>
            
            <div className="flex flex-col gap-2 mt-auto">
              <select 
                value={dispatchSelection}
                onChange={e => setDispatchSelection(e.target.value)}
                className="w-full bg-green-900 border border-green-700 text-sm text-white rounded p-2 focus:ring-1 focus:ring-white outline-none"
              >
                <option value="We need someone for a spill at Concourse N">Spill at Concourse N</option>
                <option value="Dispatch someone for crowd surge at Section B">Crowd surge at Section B</option>
                <option value="Medical emergency at Gate 1">Medical emergency at Gate 1</option>
              </select>
              <button 
                disabled={isExecuting}
                onClick={() => executeAction('Dispatch', dispatchSelection)}
                className="w-full bg-green-700 hover:bg-green-600 text-white font-medium py-2 rounded transition-colors disabled:opacity-50 flex items-center justify-center gap-2"
              >
                {isExecuting ? <Loader2 size={16} className="animate-spin" /> : <span>Dispatch Crew</span>}
              </button>
            </div>
          </div>
        </div>

      </div>

      {/* Right Panel: Monitoring Log */}
      <div className="w-1/3 border-l border-gray-800 bg-gray-900/50 flex flex-col min-h-0">
        <div className="bg-gray-900 border-b border-gray-800 text-white p-4 font-medium flex items-center gap-2">
          <Terminal size={20} className="text-fifa-grass" />
          <span>Monitoring Log</span>
        </div>
        <div className="flex-1 overflow-y-auto p-4 space-y-4 custom-scrollbar">
          {actionLogs.length === 0 ? (
            <div className="text-center text-gray-500 mt-10">
              <Terminal size={48} className="mx-auto mb-4 opacity-30" />
              <p>Execute actions to view logs here.</p>
            </div>
          ) : (
            actionLogs.map((log) => (
              <div key={log.id} className="bg-gray-800 rounded-lg p-3 border border-gray-700 shadow-sm text-sm">
                <div className="flex justify-between items-center mb-2 border-b border-gray-700 pb-2">
                  <span className={`font-bold text-xs px-2 py-0.5 rounded ${
                    log.type === 'PA' ? 'bg-blue-900/50 text-blue-300' : 'bg-green-900/50 text-green-300'
                  }`}>
                    {log.type}
                  </span>
                  <span className="text-gray-500 text-xs">
                    {log.timestamp.toLocaleTimeString()}
                  </span>
                </div>
                <div className="text-gray-200 whitespace-pre-wrap">{log.message}</div>
                {log.data && (
                  <pre className="mt-2 bg-gray-950 p-2 rounded text-xs text-gray-400 overflow-x-auto border border-gray-800">
                    {JSON.stringify(log.data, null, 2)}
                  </pre>
                )}
              </div>
            ))
          )}
          <div ref={logsEndRef} />
        </div>
      </div>
    </div>
  );
}
