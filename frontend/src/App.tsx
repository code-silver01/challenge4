import { useState } from 'react';
import { FanDashboard } from './pages/FanDashboard';
import { OrganizerDashboard } from './pages/OrganizerDashboard';
import { Splash } from './components/Splash';

function App() {
  const [role, setRole] = useState<'fan' | 'organizer'>('fan');
  const [showSplash, setShowSplash] = useState(true);

  if (showSplash) {
    return <Splash onComplete={() => setShowSplash(false)} />;
  }

  return (
    <div className="h-dvh w-screen flex flex-col font-sans overflow-hidden bg-gray-950 text-gray-100">
      {/* Global Header */}
      <header className="bg-gray-900 text-white h-14 flex items-center justify-between px-6 flex-shrink-0 z-50 shadow-md">
        <div className="flex items-center gap-2">
          <div className="w-6 h-6 bg-fifa-red rounded-sm transform rotate-45"></div>
          <span className="font-bold text-lg tracking-tight ml-2">OffsideOperations <span className="text-gray-400 font-normal">| GenAI Companion</span></span>
        </div>
        
        {/* Role Switcher */}
        <div className="flex bg-gray-800 rounded-lg p-1">
          <button
            onClick={() => setRole('fan')}
            className={`px-4 py-1 text-sm font-medium rounded-md transition-colors ${
              role === 'fan' ? 'bg-white text-gray-900 shadow' : 'text-gray-400 hover:text-white'
            }`}
          >
            Fan View
          </button>
          <button
            onClick={() => setRole('organizer')}
            className={`px-4 py-1 text-sm font-medium rounded-md transition-colors ${
              role === 'organizer' ? 'bg-white text-gray-900 shadow' : 'text-gray-400 hover:text-white'
            }`}
          >
            Organizer View
          </button>
        </div>
      </header>

      {/* Main Content Area */}
      <main className="flex-1 overflow-hidden relative">
        {role === 'fan' ? <FanDashboard /> : <OrganizerDashboard />}
      </main>
    </div>
  );
}

export default App;
