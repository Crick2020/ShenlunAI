import React from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { HistoryRecord } from '../types';
import { track } from '../services/analytics';

interface ReportProps {
  record: HistoryRecord;
  onBack: () => void;
}

const Report: React.FC<ReportProps> = ({ record, onBack }) => {
  const { result, paperName, questionTitle } = record;
  const content =
    result.modelRawOutput ??
    (record.rawGradingResponse && (record.rawGradingResponse.content ?? record.rawGradingResponse.modelRawOutput));

  const handleCopyAll = () => {
    track.reportCopy();
    const text = [
      `# 申论批改报告`,
      `**试卷**：${paperName}`,
      `**题目**：${questionTitle}`,
      ``,
      content || '',
    ].join('\n');
    navigator.clipboard.writeText(text).then(() => alert('已复制到剪贴板')).catch(() => alert('复制失败'));
  };

  return (
    <div className="max-w-5xl mx-auto px-4 md:px-6 py-6 md:py-12 pb-24">
      <div className="flex flex-col md:flex-row md:items-center justify-between mb-8 md:mb-12 gap-4 md:gap-6">
        <button
          onClick={() => { track.reportBack(); onBack(); }}
          className="group flex items-center text-[#86868b] hover:text-[#1d1d1f] transition-colors self-start"
        >
          <div className="w-8 h-8 rounded-full flex items-center justify-center bg-white shadow-sm border border-black/[0.05] mr-3 group-hover:-translate-x-1 transition-transform">
            <i className="fas fa-arrow-left text-xs"></i>
          </div>
          <span className="text-sm font-semibold">返回列表</span>
        </button>
        <button
          onClick={handleCopyAll}
          className="bg-[#1d1d1f] text-white px-6 md:px-8 py-3 rounded-2xl text-sm font-bold shadow-xl shadow-black/10 hover:bg-black transition-all"
        >
          <i className="far fa-copy mr-2"></i> 一键复制
        </button>
      </div>

      <div className="space-y-6 md:space-y-8">
        <div className="bg-white rounded-[32px] md:rounded-[48px] apple-card-shadow border border-black/[0.03] overflow-hidden">
          <div className="bg-[#f5f5f7] px-6 py-6 md:px-12 md:py-10">
            <div className="inline-block bg-[#0071e3] text-white text-[9px] md:text-[11px] font-bold px-3 py-1 rounded-full uppercase tracking-[0.1em] mb-3">
              智能深度评阅
            </div>
            <h1 className="text-xl md:text-4xl font-extrabold text-[#1d1d1f] tracking-tight leading-tight">
              {questionTitle}
            </h1>
            <p className="text-[#86868b] font-medium text-base md:text-lg mt-2">{paperName}</p>
          </div>

          <div className="p-6 md:p-12">
            <div className="prose prose-slate max-w-none prose-headings:text-[#1d1d1f] prose-p:text-[#1d1d1f] prose-li:text-[#1d1d1f] prose-strong:text-[#1d1d1f] prose-p:my-3 prose-ul:my-3 prose-ol:my-3 prose-li:my-1 prose-headings:mt-6 prose-headings:mb-3 first:prose-headings:mt-0">
              {content ? (
                <ReactMarkdown remarkPlugins={[remarkGfm]}>{content}</ReactMarkdown>
              ) : (
                <p className="text-[#86868b]">暂无批改内容</p>
              )}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};

export default Report;
