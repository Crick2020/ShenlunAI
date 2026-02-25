
import React, { useState } from 'react';
import { QuestionType } from '../types';
import { track } from '../services/analytics';

interface PaymentModalProps {
  isOpen: boolean;
  type: QuestionType;
  paperId?: string;
  onClose: () => void;
  onPay: () => void;
}

const PaymentModal: React.FC<PaymentModalProps> = ({ isOpen, type, paperId, onClose, onPay }) => {
  const [showExampleMobile, setShowExampleMobile] = useState(false);
  
  if (!isOpen) return null;
  const originalPrice = type === QuestionType.SMALL ? 0.49 : 0.99;

  return (
    <div className="fixed inset-0 z-[110] flex items-center justify-center p-0 md:p-6 lg:p-8 animate-in fade-in duration-300">
      <div className="absolute inset-0 bg-black/60 md:backdrop-blur-md" onClick={() => { track.paymentModalClose(paperId); onClose(); }}></div>
      
      <div className={`bg-white md:rounded-[48px] shadow-2xl w-full h-full md:max-w-7xl md:max-h-[92vh] overflow-hidden relative z-10 flex flex-col md:flex-row animate-in zoom-in-95 slide-in-from-bottom-10 duration-500`}>
        
        {/* Close/Back Button */}
        <button 
          onClick={() => {
            if (showExampleMobile) {
              setShowExampleMobile(false);
            } else {
              track.paymentModalClose(paperId);
              onClose();
            }
          }} 
          className="absolute top-4 right-4 md:top-6 md:right-6 z-[50] w-10 h-10 rounded-full bg-[#f5f5f7] flex items-center justify-center text-[#86868b] hover:text-[#1d1d1f] hover:bg-[#e8e8ed] transition-all shadow-sm"
        >
          <i className={`fas ${showExampleMobile ? 'fa-arrow-left' : 'fa-times'} text-sm`}></i>
        </button>

        {/* Payment Section */}
        <div className={`w-full md:w-[380px] lg:w-[420px] shrink-0 bg-white p-6 md:p-10 flex flex-col border-b md:border-b-0 md:border-r border-black/[0.05] z-20 overflow-y-auto scrollbar-hide ${showExampleMobile ? 'hidden md:flex' : 'flex'}`}>
          <div className="flex-1 flex flex-col space-y-6 md:space-y-8">
            <div className="text-center md:text-left">
              <h3 className="text-2xl md:text-3xl font-bold text-[#1d1d1f] tracking-tight">解锁深度批改</h3>
              <p className="text-[#86868b] text-sm mt-2 font-medium">支付后立享全维度专业诊断报告</p>
            </div>
            
            <div className="text-center py-8 md:py-10 bg-[#f5f5f7] rounded-[40px] border border-black/[0.02] shadow-[inset_0_2px_10px_rgba(0,0,0,0.02)]">
              <p className="text-[10px] md:text-xs font-bold text-[#86868b] uppercase tracking-[0.2em] mb-4">
                {type === QuestionType.SMALL ? '小题智能批改' : '大作文深度精批'}
              </p>
              <div className="flex flex-col items-center justify-center gap-2">
                <div className="flex items-center justify-center text-[#86868b]">
                  <span className="text-lg md:text-xl font-bold mr-1 line-through">¥</span>
                  <span className="text-2xl md:text-3xl font-bold tracking-tighter line-through">{originalPrice.toFixed(2)}</span>
                </div>
                <div className="text-[#34c759] font-black text-2xl md:text-3xl tracking-tight">限时免费</div>
              </div>
            </div>

            {/* QR Code Area - 先隐藏 */}
            <div className="hidden flex-col items-center pt-1">
              <div className="bg-white p-4 rounded-[32px] shadow-[0_15px_40px_rgba(0,0,0,0.06)] border border-black/[0.03] mb-4 group transition-transform hover:scale-105 duration-500">
                <img 
                  src="https://api.qrserver.com/v1/create-qr-code/?size=250x250&data=pay-mock" 
                  className="w-36 h-36 md:w-44 md:h-44 rounded-xl"
                  alt="Payment QR"
                />
              </div>
              <div className="flex items-center space-x-2 text-[#07c160] font-bold text-xs bg-[#07c160]/5 px-5 py-2 rounded-full border border-[#07c160]/10">
                <i className="fab fa-weixin text-base"></i>
                <span>微信扫码支付</span>
              </div>
            </div>
          </div>

          <div className="mt-6 space-y-3">
            {/* Primary Action Button (WeChat Pay Style on Mobile) */}
            <button 
              onClick={() => { track.paymentModalConfirm(paperId); onPay(); }}
              className="md:hidden w-full bg-[#07c160] text-white py-4 rounded-[20px] font-bold text-base shadow-xl shadow-green-500/20 active:scale-[0.98] transition-all flex items-center justify-center"
            >
              <span>立即批改</span>
            </button>
            
            {/* Report Example Button (Mobile Only) */}
            <button 
              onClick={() => setShowExampleMobile(true)}
              className="md:hidden w-full bg-[#f5f5f7] text-[#1d1d1f] py-3 rounded-[20px] font-bold text-[13px] flex items-center justify-center space-x-2 border border-black/[0.05]"
            >
              <i className="fas fa-file-invoice-dollar text-[#0071e3]"></i>
              <span>查看批改报告示例</span>
            </button>

            <p className="text-center text-[10px] text-[#86868b] font-medium leading-relaxed opacity-60 px-4">
              支付成功后，阅卷系统将在15-30秒内完成深度诊断报告，支持随时回看
            </p>
            {/* Mock pay button for desktop/testing */}
            <div className="hidden md:block mt-4">
              <button
                onClick={() => { track.paymentModalConfirm(paperId); onPay(); }}
                className="w-full bg-[#0071e3] text-white py-3 rounded-[12px] font-bold text-sm shadow-md hover:opacity-95 active:scale-[0.99] transition-all"
              >
                确定
              </button>
            </div>
          </div>
        </div>

        {/* Right: Detailed Example Side - Always Full in Desktop */}
        <div className={`flex-1 bg-[#fbfbfd] overflow-y-auto custom-scrollbar p-8 md:p-14 lg:p-16 ${showExampleMobile ? 'flex flex-col' : 'hidden md:flex flex-col'}`}>
          <div className="max-w-3xl mx-auto space-y-12 md:space-y-16 pb-20">
            
            {/* Header */}
            <div>
              <div className="inline-flex items-center space-x-3 bg-blue-50 text-[#0071e3] px-3 py-1 rounded-full text-[10px] font-bold uppercase tracking-widest mb-6">
                <i className="fas fa-sparkles"></i>
                <span>批改报告深度预览</span>
              </div>
              <h4 className="text-2xl md:text-3xl lg:text-4xl font-black text-[#1d1d1f] tracking-tight mb-4 leading-tight">
                2022年江苏事业单位招聘考试《综合知识和能力素质》大作文批改示例
              </h4>
              <p className="text-[#86868b] text-sm md:text-base leading-relaxed font-medium border-l-4 border-[#0071e3] pl-5 md:pl-6 py-1.5">
                本题要求结合材料关于工匠精神的名言，围绕总书记对青年的要求进行写作。
              </p>
            </div>

            {/* Part 1: Viewpoints */}
            <section className="space-y-6 md:space-y-8">
              <div className="flex items-center space-x-4 text-[#1d1d1f]">
                <div className="w-1.5 h-6 md:h-8 bg-[#0071e3] rounded-full"></div>
                <h5 className="text-xl md:text-2xl font-bold tracking-tight">核心立意与分论点解析</h5>
              </div>
              
              <div className="bg-white rounded-[32px] md:rounded-[48px] p-6 md:p-10 border border-black/[0.04] space-y-8 md:space-y-10 shadow-sm relative overflow-hidden">
                <div className="absolute top-0 right-0 w-48 h-48 bg-blue-50/30 blur-[80px] -mr-24 -mt-24"></div>
                
                <div className="p-5 md:p-7 bg-blue-50/50 rounded-2xl md:rounded-[32px] border border-blue-100/50 relative z-10">
                  <p className="text-[10px] md:text-[11px] font-bold text-[#0071e3] mb-2 tracking-widest uppercase">总论点建议</p>
                  <p className="text-[#1d1d1f] text-lg md:text-xl font-bold leading-relaxed">
                    新时代青年当以此心致一艺，以实干担重任，在民族复兴的赛道上奋勇争先。
                  </p>
                </div>

                <div className="space-y-10 md:space-y-12 relative z-10">
                  {[
                    {
                      title: '分论点一：青年当涵养“心心在一艺”的专注，筑牢理想信念，作为奋斗基石。',
                      source: '材料5：引用纪昀名言“心心在一艺”。材料6：强调青年追求进步的特质。',
                      strategy: '强调专注与热爱。青年人要沉下心来，摒弃浮躁，将个人理想融入国家发展。'
                    },
                    {
                      title: '分论点二：青年当练就“其艺必工”的本领，追求精益求精，作为成事关键。',
                      source: '材料5：沈燮元具备“扎实的编目能力”。材料6：指出施展才干的舞台无比广阔。',
                      strategy: '强调能力建设。青年不仅要有热情，更要有真才实学，在岗位上苦练内功。'
                    },
                    {
                      title: '分论点三：青年当践行“其职必举”的担当，勇于砥砺奋斗，回应时代召唤。',
                      source: '材料5：沈老觉得“工作需要”就是幸福。材料6：强调民族复兴接力赛。',
                      strategy: '强调责任担当。青年要将个人奋斗与国家命运紧密相连，在担当中历练。'
                    }
                  ].map((item, i) => (
                    <div key={i} className="relative pl-10 md:pl-14">
                      <div className="absolute left-0 top-0 w-8 h-8 md:w-10 md:h-10 rounded-full bg-[#f5f5f7] flex items-center justify-center text-xs md:text-sm font-bold text-[#1d1d1f] shadow-sm">
                        {i + 1}
                      </div>
                      <h6 className="text-base md:text-lg font-bold text-[#1d1d1f] mb-3 md:mb-5 leading-relaxed">{item.title}</h6>
                      <div className="grid grid-cols-1 md:grid-cols-2 gap-4 md:gap-6">
                        <div className="bg-[#fbfbfd] p-4 md:p-5 rounded-2xl border border-black/[0.03]">
                          <p className="text-[9px] md:text-[10px] font-bold text-[#86868b] uppercase mb-1.5 tracking-wider">分论点来源</p>
                          <p className="text-xs md:text-[14px] text-[#1d1d1f] leading-relaxed whitespace-pre-wrap font-medium opacity-90">{item.source}</p>
                        </div>
                        <div className="bg-[#fbfbfd] p-4 md:p-5 rounded-2xl border border-black/[0.03]">
                          <p className="text-[9px] md:text-[10px] font-bold text-[#86868b] uppercase mb-1.5 tracking-wider">写作思路</p>
                          <p className="text-xs md:text-[14px] text-[#1d1d1f] leading-relaxed opacity-70 italic">{item.strategy}</p>
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            </section>

            {/* Part 3: 智能诊断 */}
            <section className="space-y-6 md:space-y-8">
              <div className="flex items-center space-x-4 text-[#1d1d1f]">
                <div className="w-1.5 h-6 md:h-8 bg-[#34c759] rounded-full"></div>
                <h5 className="text-xl md:text-2xl font-bold tracking-tight">智能批改：深度报告演示</h5>
              </div>
              
              <div className="space-y-6 md:space-y-8">
                <div className="bg-white rounded-[32px] md:rounded-[48px] p-6 md:p-10 border border-black/[0.04] shadow-sm space-y-8">
                  <div className="flex flex-col md:flex-row md:items-center justify-between gap-3">
                    <h6 className="text-xl font-bold text-[#1d1d1f]">综合评价诊断</h6>
                    <div className="px-5 py-2 bg-[#34c759]/10 text-[#34c759] rounded-full text-xs font-bold w-fit border border-[#34c759]/10">预估得分：26-29分 (二类文)</div>
                  </div>
                  
                  <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 md:gap-10">
                    <div className="space-y-4">
                      <p className="text-[10px] font-bold text-[#34c759] uppercase tracking-widest border-b border-black/[0.05] pb-2">优点扫描</p>
                      <ul className="space-y-4 text-[14px] text-[#1d1d1f]/90 leading-relaxed font-medium">
                        <li className="flex items-start"><i className="fas fa-check-circle text-[#34c759] mt-1 mr-3 text-xs"></i><span>卷面极其整洁：字迹端正，无涂改，这是第一印象的高分项。</span></li>
                        <li className="flex items-start"><i className="fas fa-check-circle text-[#34c759] mt-1 mr-3 text-xs"></i><span>结构布局完整：采用了稳健的五段论证法，分论点排布清晰。</span></li>
                      </ul>
                    </div>
                    <div className="space-y-4">
                      <p className="text-[10px] font-bold text-[#ff3b30] uppercase tracking-widest border-b border-black/[0.05] pb-2">失分原因/不足</p>
                      <ul className="space-y-4 text-[14px] text-[#1d1d1f]/90 leading-relaxed font-medium">
                        <li className="flex items-start"><i className="fas fa-exclamation-circle text-[#ff3b30] mt-1 mr-3 text-xs"></i><span>立意挖掘偏浅：对“心心在一艺”的内涵停留在表面概括。</span></li>
                        <li className="flex items-start"><i className="fas fa-exclamation-circle text-[#ff3b30] mt-1 mr-3 text-xs"></i><span>论据偏离：分论点3谈论科技工具，与匠心主题脱节。</span></li>
                      </ul>
                    </div>
                  </div>
                </div>

                <div className="bg-[#f5f5f7] rounded-[32px] md:rounded-[48px] p-6 md:p-10 space-y-8">
                  <div className="space-y-5">
                    <h6 className="text-lg font-bold text-[#1d1d1f]">分论点精准度诊断 (核心改进)</h6>
                    <div className="bg-white p-6 md:p-8 rounded-3xl border border-black/[0.04] space-y-5 shadow-sm">
                      <div className="space-y-2">
                         <p className="text-sm md:text-base font-bold text-[#ff3b30] flex items-center"><i className="fas fa-microscope mr-2"></i>诊断：分论点3偏离主旨</p>
                         <p className="text-[14px] text-[#1d1d1f] leading-relaxed opacity-80">
                          您的分论点3“善于利用并转化最新科技成果”虽然符合时代背景，但偏离了题干中“心心在一艺”强调的精神品质、专注度与执着心。这属于工具论而非价值观。
                         </p>
                      </div>
                      <div className="pt-5 border-t border-black/[0.05]">
                        <p className="text-sm md:text-base font-bold text-[#0071e3] flex items-center mb-1.5"><i className="fas fa-magic mr-2"></i>优化方案：</p>
                        <p className="text-[14px] text-[#1d1d1f] font-serif-sc italic leading-relaxed">
                          建议修改为：做进步青年，当践行“其职必举”的担当，在坚守初心中砥砺奋斗。从“利用工具”转向“精神品质”的回扣。
                        </p>
                      </div>
                    </div>
                  </div>
                </div>
              </div>
            </section>

            {/* Part 4: Model Answer */}
            <section className="space-y-6 md:space-y-8">
              <div className="flex items-center space-x-4 text-[#1d1d1f]">
                <div className="w-1.5 h-6 md:h-8 bg-[#af52de] rounded-full"></div>
                <h5 className="text-xl md:text-2xl font-bold tracking-tight">高分范文参考</h5>
              </div>
              <div className="bg-[#1d1d1f] rounded-[48px] md:rounded-[64px] p-8 md:p-16 shadow-2xl relative overflow-hidden group">
                <div className="absolute top-0 right-0 w-[300px] h-[300px] bg-blue-500/10 blur-[100px] -mr-32 -mt-32"></div>
                <h6 className="text-xl md:text-2xl font-black text-white text-center mb-8 tracking-tight leading-tight">以匠心致初心 在青春赛道奋勇争先</h6>
                <div className="font-serif-sc text-base md:text-[19px] leading-[2.2] md:leading-[2.4] text-white/90 space-y-8 text-justify select-text selection:bg-blue-500/40">
                  <p>清代大儒纪昀有言：“心心在一艺，其艺必工；心心在一职，其职必举。”这道出了成就事业的底层逻辑——唯有专注热爱，方能技艺精湛；唯有尽职担当，方能有所建树。作为新时代的中国青年，更应传承“心在一艺”的匠心，跑好民族复兴的接力赛。</p>
                  <p>做进步青年，当涵养“心心在一艺”的专注，筑牢理想信念的压舱石。专注源于热爱，成于坚守。99岁的南京图书馆馆员沈燮元，一生只做两件事：编目和买书。正是这种心无旁骛的专注，让他活出了“职业最美的样子”...</p>
                  <div className="pt-6 flex justify-center">
                    <div className="h-px w-16 bg-white/20"></div>
                  </div>
                </div>
              </div>
            </section>

          </div>
        </div>
      </div>
    </div>
  );
};

export default PaymentModal;
