import { memo } from 'react';
import { useNavigate } from 'react-router-dom';
import { Home, Landmark, AlertTriangle, SlidersHorizontal } from 'lucide-react';
import { useDashboardStore } from '../../stores/dashboardStore';

export const MobileBottomNav = memo(function MobileBottomNav() {
  const navigate = useNavigate();
  const { applyPreset, activePreset, setCustomizePanelOpen } = useDashboardStore();

  const handlePreset = (presetId: string) => {
    applyPreset(presetId);
    navigate('/');
  };

  return (
    <nav className="fixed bottom-0 left-0 right-0 z-50 flex h-14 items-center justify-around border-t border-[#1C2127] bg-[#111418] md:hidden"
      style={{ paddingBottom: 'env(safe-area-inset-bottom, 0px)' }}
    >
      <button
        onClick={() => handlePreset('news')}
        className={`flex flex-1 flex-col items-center gap-0.5 py-1.5 transition-colors ${
          activePreset === 'news' ? 'text-[#2D72D2]' : 'text-[#738091]'
        }`}
      >
        <Home size={20} strokeWidth={activePreset === 'news' ? 2.2 : 1.8} />
        <span className="text-[10px] font-medium">News</span>
      </button>

      <button
        onClick={() => handlePreset('parliament')}
        className={`flex flex-1 flex-col items-center gap-0.5 py-1.5 transition-colors ${
          activePreset === 'parliament' ? 'text-[#2D72D2]' : 'text-[#738091]'
        }`}
      >
        <Landmark size={20} strokeWidth={activePreset === 'parliament' ? 2.2 : 1.8} />
        <span className="text-[10px] font-medium">Accountability</span>
      </button>

      <button
        onClick={() => handlePreset('disaster')}
        className={`flex flex-1 flex-col items-center gap-0.5 py-1.5 transition-colors ${
          activePreset === 'disaster' ? 'text-[#2D72D2]' : 'text-[#738091]'
        }`}
      >
        <AlertTriangle size={20} strokeWidth={activePreset === 'disaster' ? 2.2 : 1.8} />
        <span className="text-[10px] font-medium">Alerts</span>
      </button>

      <button
        onClick={() => setCustomizePanelOpen(true)}
        className="flex flex-1 flex-col items-center gap-0.5 py-1.5 transition-colors text-[#738091]"
      >
        <SlidersHorizontal size={20} strokeWidth={1.8} />
        <span className="text-[10px] font-medium">Customize</span>
      </button>
    </nav>
  );
});
