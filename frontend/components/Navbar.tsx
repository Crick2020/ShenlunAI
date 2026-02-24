
import React from 'react';
import { User } from '../types';
import { track } from '../services/analytics';

interface NavbarProps {
  user: User | null;
  onLogin: () => void;
  onLogout: () => void;
  onNavigate: (page: string) => void;
}

const Navbar: React.FC<NavbarProps> = ({ user, onLogin, onLogout, onNavigate }) => {
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

          <div className="flex items-center space-x-3 md:space-x-4">
            {user ? (
              <div className="flex items-center space-x-2 md:space-x-3 group relative cursor-pointer">
                <div className="flex flex-col items-end">
                  <span className="text-[12px] md:text-[13px] font-semibold text-[#1d1d1f] leading-none">{user.nickname}</span>
                  <span className="text-[9px] md:text-[10px] text-[#86868b] mt-1 hidden sm:block">普通用户</span>
                </div>
                <img src={user.avatar} className="w-8 h-8 md:w-9 md:h-9 rounded-full border border-black/5 ring-2 md:ring-4 ring-white shadow-sm" alt="avatar" />
                
                <div className="hidden group-hover:block absolute right-0 top-full pt-2 md:pt-3 w-36 md:w-40 animate-in fade-in slide-in-from-top-2 duration-200">
                  <div className="bg-white rounded-xl md:rounded-2xl border border-black/[0.05] shadow-2xl overflow-hidden py-1">
                    <button onClick={() => { track.navClick('profile'); onNavigate('profile'); }} className="flex items-center space-x-2 w-full text-left px-4 py-2 text-sm hover:bg-[#f5f5f7] transition-colors">
                      <i className="far fa-user-circle w-5"></i>
                      <span>个人中心</span>
                    </button>
                    <div className="h-px bg-black/[0.05] mx-3 my-1"></div>
                    <button onClick={() => { track.navClick('logout'); onLogout(); }} className="flex items-center space-x-2 w-full text-left px-4 py-2 text-sm hover:bg-[#f5f5f7] transition-colors text-red-500">
                      <i className="fas fa-trash-alt w-5"></i>
                      <span>清除缓存</span>
                    </button>
                  </div>
                </div>
              </div>
            ) : null}
          </div>
        </div>
      </div>
    </nav>
  );
};

export default Navbar;
