import React, { useState, useRef, useEffect } from 'react';
import { track } from '../services/analytics';
import { getFeedbackUrl, CHANGELOG_URL } from '../constants';

interface NavbarProps {
  onNavigate: (page: string) => void;
}

const Navbar: React.FC<NavbarProps> = ({ onNavigate }) => {
  const [moreOpen, setMoreOpen] = useState(false);
  const menuRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const handleClickOutside = (e: MouseEvent) => {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) {
        setMoreOpen(false);
      }
    };
    document.addEventListener('click', handleClickOutside);
    return () => document.removeEventListener('click', handleClickOutside);
  }, []);

  const openFeedback = () => {
    setMoreOpen(false);
    track.navClick('feedback');
    window.open(getFeedbackUrl(), '_blank', 'noopener,noreferrer');
  };

  const openChangelog = () => {
    setMoreOpen(false);
    track.navClick('changelog');
    window.open(CHANGELOG_URL, '_blank', 'noopener,noreferrer');
  };

  return (
    <nav className="apple-blur sticky top-0 z-[60] border-b border-black/[0.05]">
      <div className="max-w-7xl mx-auto px-4 md:px-6">
        <div className="flex justify-between h-14 md:h-16 items-center">
          <div className="flex items-center space-x-2 md:space-x-3 cursor-pointer group" onClick={() => { track.navClick('home'); onNavigate('home'); }}>
            <div className="bg-[#0071e3] text-white w-8 h-8 md:w-9 md:h-9 rounded-lg md:rounded-xl flex items-center justify-center shadow-lg shadow-blue-500/20 group-hover:scale-105 transition-transform duration-300">
              <i className="fas fa-feather-pointed text-base md:text-lg"></i>
            </div>
            <span className="text-lg md:text-xl font-bold tracking-tight text-[#1d1d1f]">申论智能批改</span>
          </div>

          <div className="hidden md:flex items-center space-x-8 lg:space-x-10">
            <button onClick={() => { track.navClick('list'); onNavigate('home'); }} className="text-sm font-medium text-[#1d1d1f]/70 hover:text-[#0071e3] transition-colors">题库列表</button>
            <button onClick={() => { track.navClick('history'); onNavigate('profile'); }} className="text-sm font-medium text-[#1d1d1f]/70 hover:text-[#0071e3] transition-colors">历史批改</button>
          </div>

          <div className="flex items-center" ref={menuRef}>
            <button
              onClick={() => setMoreOpen((v) => !v)}
              className={`flex items-center gap-2 px-4 py-2 rounded-full text-[13px] md:text-[14px] font-semibold text-[#1d1d1f] transition-all duration-200 ${
                moreOpen ? 'bg-[#e5e5ea]' : 'bg-[#f5f5f7] hover:bg-[#e8e8ed] active:bg-[#e5e5ea]'
              }`}
              aria-expanded={moreOpen}
              aria-haspopup="true"
              aria-label="更多"
            >
              <span>更多</span>
              <i className={`fas fa-chevron-down text-[10px] text-[#86868b] transition-transform duration-200 ${moreOpen ? 'rotate-180' : ''}`} />
            </button>

            {moreOpen && (
              <div className="absolute right-4 md:right-6 top-full mt-2 w-44 rounded-2xl apple-more-menu py-2 z-[70] animate-in fade-in slide-in-from-top-2 duration-200">
                <button
                  onClick={() => { setMoreOpen(false); track.navClick('profile'); onNavigate('profile'); }}
                  className="apple-more-item flex items-center gap-3 w-full text-left px-4 py-3 text-[14px] text-[#1d1d1f]"
                >
                  <div className="apple-more-icon bg-[#0071e3]/10 shrink-0">
                    <i className="far fa-clock text-[14px] text-[#0071e3]" />
                  </div>
                  <span>批改历史</span>
                </button>
                <button
                  onClick={openFeedback}
                  className="apple-more-item flex items-center gap-3 w-full text-left px-4 py-3 text-[14px] text-[#1d1d1f]"
                >
                  <div className="apple-more-icon bg-[#34c759]/10 shrink-0">
                    <i className="far fa-comment-dots text-[14px] text-[#34c759]" />
                  </div>
                  <span>意见建议</span>
                </button>
                <button
                  onClick={openChangelog}
                  className="apple-more-item flex items-center gap-3 w-full text-left px-4 py-3 text-[14px] text-[#1d1d1f]"
                >
                  <div className="apple-more-icon bg-[#af52de]/10 shrink-0">
                    <i className="fas fa-clipboard-list text-[14px] text-[#af52de]" />
                  </div>
                  <span>更新日志</span>
                </button>
              </div>
            )}
          </div>
        </div>
      </div>
    </nav>
  );
};

export default Navbar;
