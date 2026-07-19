import { useEffect, useState } from 'react';

export function Splash({ onComplete }: { onComplete: () => void }) {
  const [opacity, setOpacity] = useState(1);

  useEffect(() => {
    // Fade out after 2.5 seconds, then call onComplete
    const timer1 = setTimeout(() => setOpacity(0), 2000);
    const timer2 = setTimeout(onComplete, 2500);

    return () => {
      clearTimeout(timer1);
      clearTimeout(timer2);
    };
  }, [onComplete]);

  return (
    <div 
      className="fixed inset-0 z-[100] flex flex-col items-center justify-center bg-gray-950 transition-opacity duration-500 ease-in-out overflow-hidden"
      style={{ opacity }}
    >
      <div className="relative flex flex-col items-center w-full max-w-md">
        
        {/* Kickoff Animation SVG */}
        <div className="w-full h-48 relative mb-8 flex justify-center items-center">
          <svg viewBox="0 0 400 200" className="w-full h-full">
            {/* Pitch */}
            <rect x="0" y="50" width="400" height="100" fill="#2d6a4f" rx="10" />
            <line x1="200" y1="50" x2="200" y2="150" stroke="#fff" strokeWidth="2" opacity="0.6" />
            <circle cx="200" cy="100" r="30" fill="none" stroke="#fff" strokeWidth="2" opacity="0.6" />
            
            {/* Ball path */}
            <path d="M 50 100 Q 200 -50 350 100" fill="none" stroke="none" id="kickPath" />
            
            {/* Animated Ball */}
            <circle cx="0" cy="0" r="8" fill="#fff" filter="drop-shadow(0px 4px 2px rgba(0,0,0,0.5))">
              <animateMotion dur="1.5s" fill="freeze" calcMode="spline" keyTimes="0;1" keySplines="0.4 0 0.2 1">
                <mpath href="#kickPath" />
              </animateMotion>
              <animateTransform attributeName="transform" type="scale" values="1;1.5;1" dur="1.5s" fill="freeze" />
            </circle>
          </svg>
        </div>
        
        {/* Text Branding */}
        <h1 className="text-5xl font-extrabold text-white tracking-tight mb-2 animate-pulse">Setu</h1>
        <h2 className="text-xl text-fifa-grass font-semibold tracking-widest uppercase mb-8">World Cup 26</h2>
        
        {/* Loading Bar */}
        <div className="w-48 h-1 bg-gray-800 rounded-full overflow-hidden">
          <div className="h-full bg-fifa-grass animate-[translate-x_2s_ease-in-out_infinite]" style={{ width: '50%', transformOrigin: 'left', animationName: 'loading' }}></div>
        </div>
      </div>
      
      <style>{`
        @keyframes loading {
          0% { transform: translateX(-100%); }
          100% { transform: translateX(200%); }
        }
      `}</style>
    </div>
  );
}
