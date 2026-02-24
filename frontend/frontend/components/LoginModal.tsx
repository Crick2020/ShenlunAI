
import React from 'react';

interface LoginModalProps {
  isOpen: boolean;
  onClose: () => void;
  onSuccess: () => void;
}

const LoginModal: React.FC<LoginModalProps> = ({ isOpen, onClose, onSuccess }) => {
  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-[100] flex items-center justify-center p-6 animate-in fade-in duration-300">
      <div className="absolute inset-0 bg-black/40 backdrop-blur-sm" onClick={onClose}></div>
      <div className="bg-white rounded-[40px] shadow-2xl w-full max-w-sm overflow-hidden relative z-10 animate-in zoom-in-95 slide-in-from-bottom-10 duration-500 apple-card-shadow">
        <div className="p-10 text-center">
          <div className="flex justify-end absolute top-6 right-6">
            <button onClick={onClose} className="w-8 h-8 rounded-full bg-[#f5f5f7] flex items-center justify-center text-[#86868b] hover:text-[#1d1d1f] transition-colors">
              <i className="fas fa-times text-xs"></i>
            </button>
          </div>
          
          <div className="w-16 h-16 bg-[#07c160]/10 text-[#07c160] rounded-2xl flex items-center justify-center mx-auto mb-6">
            <i className="fab fa-weixin text-3xl"></i>
          </div>
          
          <h2 className="text-2xl font-bold text-[#1d1d1f] mb-2 tracking-tight">微信扫码登录</h2>
          <p className="text-[#86868b] text-sm font-medium mb-10">首次扫码即可完成自动注册</p>
          
          <div className="bg-[#f5f5f7] p-8 rounded-[32px] flex items-center justify-center relative group overflow-hidden border border-black/[0.03]">
            <img 
              src="https://api.qrserver.com/v1/create-qr-code/?size=200x200&data=https://github.com/google-gemini" 
              className="w-44 h-44 rounded-2xl border-4 border-white shadow-sm transition-all duration-500 group-hover:blur-md"
              alt="QR Code"
            />
            <div className="absolute inset-0 flex items-center justify-center opacity-0 group-hover:opacity-100 transition-all duration-500">
              <button 
                onClick={onSuccess}
                className="bg-[#07c160] text-white px-8 py-3 rounded-full font-bold shadow-xl shadow-green-500/20 active:scale-95 transition-transform"
              >
                模拟扫码成功
              </button>
            </div>
          </div>
          
          <div className="mt-10 text-[13px] text-[#86868b] font-medium leading-relaxed">
            请使用微信扫描二维码登录<br/>开启您的申论提分之旅
          </div>
        </div>
        <div className="bg-[#f5f5f7] px-10 py-5 text-center">
          <p className="text-[11px] text-[#86868b] font-medium leading-relaxed">
            登录即代表您同意 <span className="text-[#0071e3] hover:underline cursor-pointer">服务协议</span> 和 <span className="text-[#0071e3] hover:underline cursor-pointer">隐私政策</span>
          </p>
        </div>
      </div>
    </div>
  );
};

export default LoginModal;
