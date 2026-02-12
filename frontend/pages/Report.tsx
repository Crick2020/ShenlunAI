import React, { useState } from 'react';
import ReactMarkdown from 'react-markdown';
import { GradingResult, HistoryRecord } from '../types';
import { Radar, RadarChart, PolarGrid, PolarAngleAxis, PolarRadiusAxis, ResponsiveContainer } from 'recharts';

interface ReportProps {
  record: HistoryRecord;
  onBack: () => void;
}

const Report: React.FC<ReportProps> = ({ record, onBack }) => {
  const { result, userAnswer, paperName, questionTitle, rawGradingResponse } = record;
  const [showRawJson, setShowRawJson] = useState(false);
  const rawText = result.modelRawOutput ?? rawGradingResponse?.modelRawOutput ?? '';
  const hasFullRaw = rawText || (rawGradingResponse && Object.keys(rawGradingResponse).length > 0);

  // 兜底：防止后端未返回 radarData 导致前端报错
  const safeRadar = result.radarData || {
    points: 0,
    logic: 0,
    language: 0,
    format: 0,
  };

  const radarData = [
    { subject: '要点', A: safeRadar.points ?? 0, fullMark: 100 },
    { subject: '逻辑', A: safeRadar.logic ?? 0, fullMark: 100 },
    { subject: '语言', A: safeRadar.language ?? 0, fullMark: 100 },
    { subject: '规范', A: safeRadar.format ?? 0, fullMark: 100 },
  ];

  const handleCopyAll = () => {
    const parts = [
      `# 申论批改报告`,
      `**试卷**：${paperName}`,
      `**题目**：${questionTitle}`,
      `**得分**：${result.score} / ${result.maxScore}`,
      ``,
      `## 专家总评`,
      result.overallEvaluation,
      ``,
      `## 考生作答`,
      userAnswer,
      ``,
      `## 参考答案`,
      result.modelAnswer,
    ];
    if (result.detailedComments?.length) {
      parts.push(``, `## 逐句点评`);
      result.detailedComments.forEach((c: any, i: number) => {
        parts.push(`${i + 1}. "${c.originalText}"`, `${c.comment}`, ``);
      });
    }
    const text = parts.join('\n');
    navigator.clipboard.writeText(text).then(() => alert('已复制到剪贴板')).catch(() => alert('复制失败'));
  };

  return (
    <div className="max-w-5xl mx-auto px-4 md:px-6 py-6 md:py-12 pb-24">
      {/* Header Controls */}
      <div className="flex flex-col md:flex-row md:items-center justify-between mb-8 md:mb-12 gap-4 md:gap-6">
        <button onClick={onBack} className="group flex items-center text-[#86868b] hover:text-[#1d1d1f] transition-colors self-start">
          <div className="w-8 h-8 rounded-full flex items-center justify-center bg-white shadow-sm border border-black/[0.05] mr-3 group-hover:-translate-x-1 transition-transform">
            <i className="fas fa-arrow-left text-xs"></i>
          </div>
          <span className="text-sm font-semibold">返回列表</span>
        </button>
        <button onClick={handleCopyAll} className="bg-[#1d1d1f] text-white px-6 md:px-8 py-3 rounded-2xl text-sm font-bold shadow-xl shadow-black/10 hover:bg-black transition-all">
          <i className="far fa-copy mr-2"></i> 一键复制
        </button>
      </div>

      <div className="space-y-8 md:space-y-10">
        {/* Main Summary Card */}
        <div className="bg-white rounded-[32px] md:rounded-[48px] apple-card-shadow border border-black/[0.03] overflow-hidden">
          <div className="bg-[#f5f5f7] px-6 py-8 md:px-16 md:py-16">
            <div className="flex flex-col md:flex-row justify-between items-start gap-8 md:gap-10">
              <div className="flex-1 space-y-3 md:space-y-4">
                <div className="inline-block bg-[#0071e3] text-white text-[9px] md:text-[11px] font-bold px-3 py-1 rounded-full uppercase tracking-[0.1em]">AI 智能深度评阅</div>
                <h1 className="text-2xl md:text-5xl font-extrabold text-[#1d1d1f] tracking-tight leading-tight">{questionTitle}</h1>
                <p className="text-[#86868b] font-medium text-base md:text-lg">{paperName}</p>
              </div>
              <div className="flex flex-row md:flex-col items-center justify-between md:justify-center p-6 md:p-8 bg-white rounded-3xl shadow-sm border border-black/[0.03] w-full md:w-auto min-w-[180px]">
                <span className="text-[10px] md:text-[11px] font-bold text-[#86868b] uppercase tracking-widest">综合得分</span>
                <div className="flex items-baseline">
                  <span className="text-5xl md:text-7xl font-black text-[#1d1d1f] tracking-tighter">{result.score}</span>
                  <span className="text-lg md:text-xl font-bold text-[#86868b] ml-2">/ {result.maxScore}</span>
                </div>
              </div>
            </div>
          </div>

          <div className="p-6 md:p-16">
            <div className="grid grid-cols-1 lg:grid-cols-5 gap-10 md:gap-16">
              {/* Radar Analysis */}
              <div className="lg:col-span-2 space-y-4 md:space-y-6">
                <h3 className="text-lg md:text-xl font-bold text-[#1d1d1f] flex items-center">
                  <span className="w-1 md:w-1.5 h-6 bg-[#0071e3] rounded-full mr-3"></span>
                  作答能力透视
                </h3>
                <div className="h-60 md:h-80 bg-[#fbfbfd] rounded-3xl p-4">
                  <ResponsiveContainer width="100%" height="100%">
                    <RadarChart cx="50%" cy="50%" outerRadius="80%" data={radarData}>
                      <PolarGrid stroke="#d1d1d6" strokeDasharray="3 3" />
                      <PolarAngleAxis dataKey="subject" tick={{fontSize: 12, fontWeight: 600, fill: '#1d1d1f'}} />
                      <PolarRadiusAxis angle={30} domain={[0, 100]} tick={false} />
                      <Radar name="评分" dataKey="A" stroke="#0071e3" strokeWidth={3} fill="#0071e3" fillOpacity={0.15} />
                    </RadarChart>
                  </ResponsiveContainer>
                </div>
              </div>

              {/* Overall Evaluation */}
              <div className="lg:col-span-3 space-y-4 md:space-y-6">
                <h3 className="text-lg md:text-xl font-bold text-[#1d1d1f] flex items-center">
                  <span className="w-1 md:w-1.5 h-6 bg-[#34c759] rounded-full mr-3"></span>
                  专家级总评
                </h3>
                <div className="bg-[#fbfbfd] rounded-3xl p-6 md:p-10 relative prose prose-slate max-w-none">
                  <div className="relative z-10 text-[#1d1d1f] leading-[1.8] text-base md:text-lg">
                    <ReactMarkdown>{result.overallEvaluation || ''}</ReactMarkdown>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>

        {/* Content Details Grid */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-8 md:gap-10">
          {/* User Answer Card */}
          <div className="bg-white rounded-3xl md:rounded-[40px] apple-card-shadow border border-black/[0.03] p-6 md:p-10 space-y-6">
            <h3 className="text-lg md:text-xl font-bold text-[#1d1d1f]">考生原卷</h3>
            <div className="font-serif-sc text-base md:text-lg leading-[2] text-[#1d1d1f] bg-[#fbfbfd] p-6 md:p-8 rounded-2xl border border-black/[0.02]">
              {userAnswer}
            </div>
          </div>

          {/* Detailed Comments */}
          <div className="bg-white rounded-3xl md:rounded-[40px] apple-card-shadow border border-black/[0.03] p-6 md:p-10 space-y-6">
            <h3 className="text-lg md:text-xl font-bold text-[#1d1d1f]">逐句点评</h3>
            <div className="space-y-3 md:space-y-4">
              {result.detailedComments.map((comment, i) => (
                <div key={i} className={`p-4 md:p-6 rounded-2xl border transition-all duration-300 ${comment.type === 'positive' ? 'bg-[#34c759]/5 border-[#34c759]/10' : 'bg-[#ff3b30]/5 border-[#ff3b30]/10'}`}>
                  <div className="flex items-start space-x-3 md:space-x-4">
                    <div className={`w-7 h-7 md:w-8 md:h-8 rounded-full flex items-center justify-center shrink-0 ${comment.type === 'positive' ? 'bg-[#34c759] text-white' : 'bg-[#ff3b30] text-white'}`}>
                      <i className={`fas ${comment.type === 'positive' ? 'fa-check' : 'fa-info'} text-[9px] md:text-[10px]`}></i>
                    </div>
                    <div>
                      <p className="text-[#1d1d1f] font-bold text-xs md:text-sm mb-2 opacity-80 italic">“{comment.originalText}”</p>
                      <div className="text-[#86868b] text-[14px] md:text-[15px] font-medium leading-relaxed"><ReactMarkdown>{comment.comment || ''}</ReactMarkdown></div>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>

        {/* Model Answer Full Width */}
        <div className="bg-[#1d1d1f] rounded-3xl md:rounded-[48px] p-8 md:p-16 shadow-2xl overflow-hidden relative group">
          <div className="relative z-10">
            <div className="flex items-center space-x-3 md:space-x-4 mb-6 md:mb-10">
              <div className="bg-blue-500 w-10 h-10 md:w-12 md:h-12 rounded-xl md:rounded-2xl flex items-center justify-center text-white">
                <i className="fas fa-lightbulb"></i>
              </div>
              <h3 className="text-xl md:text-2xl font-bold text-white">高分参考范文</h3>
            </div>
            <div className="font-serif-sc text-lg md:text-xl leading-[2] md:leading-[2.4] text-white/90 select-text selection:bg-blue-500/30 prose prose-invert prose-p:my-2 max-w-none">
              <ReactMarkdown>{result.modelAnswer || ''}</ReactMarkdown>
            </div>
          </div>
        </div>

        {/* AI 完整返回：原文 + 解析后 JSON */}
        {hasFullRaw && (
          <div className="bg-white rounded-3xl md:rounded-[40px] apple-card-shadow border border-black/[0.06] overflow-hidden">
            <div className="px-6 py-4 md:px-10 md:py-6 border-b border-black/[0.06] bg-[#f5f5f7]">
              <h3 className="text-lg md:text-xl font-bold text-[#1d1d1f] flex items-center">
                <span className="w-1.5 h-6 bg-[#0071e3] rounded-full mr-3"></span>
                AI 批改完整返回
              </h3>
              <p className="text-[#86868b] text-sm mt-1">以下为模型返回的全文（文本/JSON），便于核对与调试。</p>
            </div>
            <div className="p-6 md:p-10 space-y-6">
              {rawText && (
                <div>
                  <h4 className="text-sm font-bold text-[#86868b] uppercase tracking-wider mb-2">模型原始输出</h4>
                  <pre className="bg-[#1d1d1f] text-white/90 text-sm md:text-base rounded-2xl p-4 md:p-6 overflow-auto max-h-[50vh] whitespace-pre-wrap break-words font-mono select-text">
                    {rawText}
                  </pre>
                </div>
              )}
              {rawGradingResponse && (
                <div>
                  <button
                    type="button"
                    onClick={() => setShowRawJson(!showRawJson)}
                    className="text-sm font-semibold text-[#0071e3] hover:underline mb-2"
                  >
                    {showRawJson ? '收起' : '展开'}解析后完整数据 (JSON)
                  </button>
                  {showRawJson && (
                    <pre className="bg-[#fbfbfd] border border-black/[0.08] text-[#1d1d1f] text-xs md:text-sm rounded-2xl p-4 md:p-6 overflow-auto max-h-[60vh] whitespace-pre-wrap break-words font-mono select-text">
                      {JSON.stringify(rawGradingResponse, null, 2)}
                    </pre>
                  )}
                </div>
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  );
};

export default Report;
