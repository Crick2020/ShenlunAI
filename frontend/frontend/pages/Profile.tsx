
import React from 'react';
import { HistoryRecord } from '../types';

interface ProfileProps {
  history: HistoryRecord[];
  onViewRecord: (record: HistoryRecord) => void;
}

const Profile: React.FC<ProfileProps> = ({ history, onViewRecord }) => {
  return (
    <div className="max-w-5xl mx-auto px-4 py-6 md:py-12">
      <div className="mb-6 md:mb-10">
        <h1 className="text-2xl md:text-3xl font-bold text-[#1d1d1f]">历史批改</h1>
        <p className="text-[#86868b] text-sm mt-1">累计完成 {history.length} 次深度批改</p>
      </div>

      {history.length > 0 ? (
        <div className="space-y-3 md:space-y-4">
          {history.map(record => (
            <div 
              key={record.id} 
              className="bg-white rounded-2xl md:rounded-[32px] border border-black/[0.05] p-5 md:p-8 flex flex-col md:flex-row justify-between items-stretch md:items-center hover:shadow-lg transition-all cursor-pointer group apple-card-shadow"
              onClick={() => onViewRecord(record)}
            >
              <div className="flex-1 space-y-1 md:space-y-2">
                <div className="flex items-center space-x-2">
                  <span className="text-[9px] md:text-[10px] bg-blue-50 text-[#0071e3] px-2 py-0.5 rounded font-bold uppercase tracking-wider">深度精批</span>
                  <h3 className="font-bold text-[#1d1d1f] text-sm md:text-lg truncate max-w-[260px] md:max-w-none">{record.paperName}</h3>
                </div>
                <p className="text-[12px] md:text-[14px] text-[#86868b] truncate">{record.questionTitle}</p>
                <div className="flex items-center space-x-4 pt-1 text-[10px] md:text-[11px] text-[#86868b] font-medium">
                  <span><i className="far fa-calendar mr-1.5"></i> {new Date(record.timestamp).toLocaleDateString()}</span>
                  <span><i className="fas fa-keyboard mr-1.5"></i> {record.userAnswer.length} 字</span>
                </div>
              </div>
              <div className="mt-4 md:mt-0 md:ml-8 flex items-center justify-end shrink-0 border-t md:border-t-0 pt-4 md:pt-0">
                <div className="bg-[#f5f5f7] group-hover:bg-[#0071e3] group-hover:text-white transition-all w-10 h-10 md:w-12 md:h-12 rounded-full flex items-center justify-center text-[#86868b] shadow-sm">
                  <i className="fas fa-chevron-right text-[10px] md:text-xs"></i>
                </div>
              </div>
            </div>
          ))}
        </div>
      ) : (
        <div className="bg-white rounded-[32px] md:rounded-[40px] border border-dashed border-black/10 py-16 md:py-24 text-center mx-2">
          <div className="w-16 h-16 md:w-20 md:h-20 bg-[#f5f5f7] rounded-[24px] md:rounded-[28px] flex items-center justify-center mx-auto mb-6 text-[#d1d1d6]">
            <i className="fas fa-history text-2xl md:text-3xl"></i>
          </div>
          <p className="text-[#1d1d1f] font-bold text-base md:text-lg">暂无批改记录</p>
          <p className="text-[#86868b] text-sm mt-1 px-10">完成您的第一次批改后，报告将出现在这里</p>
        </div>
      )}
    </div>
  );
};

export default Profile;
