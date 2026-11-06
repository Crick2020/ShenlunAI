import React from 'react';
import { PRIVACY_POLICY_URL, USER_AGREEMENT_URL } from '../constants';

interface PrivacyConsentModalProps {
  onAgree: () => void;
  onDisagree: () => void;
}

const PrivacyConsentModal: React.FC<PrivacyConsentModalProps> = ({ onAgree, onDisagree }) => {
  return (
    <div className="fixed inset-0 z-[300] flex items-center justify-center bg-black/55 p-4">
      <div className="w-full max-w-lg overflow-hidden rounded-[28px] bg-white shadow-2xl">
        <div className="px-6 pb-5 pt-7 text-center md:px-8">
          <div className="mx-auto mb-4 flex h-14 w-14 items-center justify-center rounded-2xl bg-[#0071e3]/10 text-[#0071e3]">
            <i className="fas fa-shield-halved text-2xl" />
          </div>
          <h1 className="text-xl font-bold tracking-tight text-[#1d1d1f]">个人信息保护指引</h1>
          <p className="mt-3 text-left text-[14px] leading-7 text-[#636366]">
            欢迎使用爱学申论！我们深知个人信息对你的重要性。为了向你提供试卷浏览、在线作答、AI
            批改、批改历史和性能保障等服务，我们会在你同意后处理必要信息。
          </p>

          <div className="mt-3 space-y-2 text-left text-[13px] leading-6 text-[#636366]">
            <p>
              <strong className="text-[#1d1d1f]">1. 作答信息：</strong>
              你提交的文字答案、答题图片及对应题目，将用于生成批改报告。
            </p>
            <p>
              <strong className="text-[#1d1d1f]">2. 设备与日志信息：</strong>
              为完成统计分析、崩溃诊断和安全风控，我们可能收集设备型号、设备标识符（如 OAID）、操作系统版本、应用版本、网络状态及日志信息。
            </p>
            <p>
              <strong className="text-[#1d1d1f]">3. 相机与相册权限：</strong>
              仅在你主动拍照或选择图片时申请，拒绝后仍可使用文字作答。
            </p>
          </div>

          <p className="mt-4 text-left text-[13px] leading-6 text-[#86868b]">
            请先阅读
            <a
              href={USER_AGREEMENT_URL}
              target="_blank"
              rel="noopener noreferrer"
              className="mx-1 font-semibold text-[#0071e3]"
            >
              《用户协议》
            </a>
            和
            <a
              href={PRIVACY_POLICY_URL}
              target="_blank"
              rel="noopener noreferrer"
              className="mx-1 font-semibold text-[#0071e3]"
            >
              《隐私政策》
            </a>
            。点击“同意并继续”即表示你已阅读并同意上述内容。
          </p>
        </div>

        <div className="flex gap-3 border-t border-black/[0.06] p-4">
          <button
            type="button"
            onClick={onDisagree}
            className="flex-1 rounded-2xl border border-black/[0.08] bg-white px-4 py-3.5 text-[15px] font-semibold text-[#636366] active:scale-[0.98]"
          >
            不同意
          </button>
          <button
            type="button"
            onClick={onAgree}
            className="flex-[1.35] rounded-2xl bg-[#0071e3] px-4 py-3.5 text-[15px] font-bold text-white shadow-lg shadow-blue-500/20 active:scale-[0.98]"
          >
            同意并继续
          </button>
        </div>
      </div>
    </div>
  );
};

export default PrivacyConsentModal;
