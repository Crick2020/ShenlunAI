import React, { useState, useRef, useEffect } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { HistoryRecord } from '../types';
import { track } from '../services/analytics';
import { openFeedback, CHANGELOG_URL } from '../constants';
import { formatModelEssayAsGrid, normalizeReportMarkdown, reportMarkdownToPlainText } from '../utils/normalizeReportMarkdown';

interface ReportProps {
  record: HistoryRecord;
  onBack: () => void;
}

interface ModelEssaySplit {
  before: string;
  body: string;
  after: string;
}

function splitModelEssay(markdown: string): ModelEssaySplit | null {
  if (!markdown) return null;
  const lines = markdown.split('\n');
  const start = lines.findIndex((line) => /(?:^|\s)(?:#+\s*)?(?:\*\*)?\s*标杆范文[:：]/.test(line));
  if (start < 0) return null;

  const isNextSectionHeader = (line: string): boolean => {
    const trimmed = line.trim();
    if (!trimmed) return false;
    if (/^#{1,6}\s+/.test(trimmed)) return true;
    if (/^(?:\*\*)?\s*范文解析[:：]/.test(trimmed)) return true;
    if (/^(?:\*\*)?\s*金句积累[:：]/.test(trimmed)) return true;
    if (/^(?:模块|【)/.test(trimmed) && !/标杆范文/.test(trimmed)) return true;
    return false;
  };

  let end = lines.length;
  for (let i = start + 1; i < lines.length; i += 1) {
    if (isNextSectionHeader(lines[i])) {
      end = i;
      break;
    }
  }

  const before = lines.slice(0, start + 1).join('\n');
  const body = lines.slice(start + 1, end).join('\n').trim();
  const after = lines.slice(end).join('\n');
  return { before, body, after };
}

const Report: React.FC<ReportProps> = ({ record, onBack }) => {
  const { result, paperName, questionTitle } = record;
  const [moreOpen, setMoreOpen] = useState(false);
  const moreMenuRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const handleClickOutside = (e: MouseEvent) => {
      if (moreMenuRef.current && !moreMenuRef.current.contains(e.target as Node)) setMoreOpen(false);
    };
    document.addEventListener('click', handleClickOutside);
    return () => document.removeEventListener('click', handleClickOutside);
  }, []);
  const rawContent =
    result.modelRawOutput ??
    (record.rawGradingResponse && (record.rawGradingResponse.content ?? record.rawGradingResponse.modelRawOutput));
  const content = rawContent ? formatModelEssayAsGrid(normalizeReportMarkdown(rawContent)) : '';
  const modelEssaySplit = splitModelEssay(content);
  const modelEssayRows = modelEssaySplit?.body
    ? modelEssaySplit.body
      .split('\n')
      .map((row) => row.trim())
      .filter(Boolean)
    : [];

  const handleCopyAll = () => {
    track.reportCopy();
    const mdBody = rawContent ? normalizeReportMarkdown(rawContent) : '';
    const bodyPlain = reportMarkdownToPlainText(mdBody);
    const text = ['申论批改报告', `试卷：${paperName}`, `题目：${questionTitle}`, '', bodyPlain].join('\n');
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
        <div className="flex items-center gap-3">
          <div className="relative" ref={moreMenuRef}>
            <button
              onClick={() => setMoreOpen((v) => !v)}
              className={`w-10 h-10 rounded-full flex items-center justify-center text-[#1d1d1f] transition-all duration-200 ${
                moreOpen ? 'bg-[#e5e5ea]' : 'bg-[#f5f5f7] hover:bg-[#e8e8ed] active:bg-[#e5e5ea] border border-black/[0.06]'
              }`}
              aria-label="更多"
            >
              <i className="fas fa-ellipsis text-[15px]" />
            </button>
            {moreOpen && (
              <div className="absolute right-0 top-full mt-2 w-40 rounded-2xl apple-more-menu py-2 z-50 animate-in fade-in slide-in-from-top-2 duration-200">
                <button
                  onClick={() => { setMoreOpen(false); openFeedback({ name: paperName }); }}
                  className="apple-more-item flex items-center gap-3 w-full text-left px-4 py-3 text-[14px] text-[#1d1d1f]"
                >
                  <div className="apple-more-icon bg-[#34c759]/10 shrink-0">
                    <i className="far fa-comment-dots text-[14px] text-[#34c759]" />
                  </div>
                  <span>意见建议</span>
                </button>
                <button
                  onClick={() => { setMoreOpen(false); window.open(CHANGELOG_URL, '_blank', 'noopener,noreferrer'); }}
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
          <button
            onClick={handleCopyAll}
            className="bg-[#1d1d1f] text-white px-6 md:px-8 py-3 rounded-2xl text-sm font-bold shadow-xl shadow-black/10 hover:bg-black transition-all"
          >
            <i className="far fa-copy mr-2"></i> 一键复制
          </button>
        </div>
      </div>

      <div className="space-y-6 md:space-y-8">
        <div className="bg-white rounded-[32px] md:rounded-[48px] apple-card-shadow border border-black/[0.03] overflow-visible">
          <div className="bg-[#f5f5f7] px-6 py-6 md:px-12 md:py-10 rounded-t-[32px] md:rounded-t-[48px]">
            <div className="inline-block bg-[#0071e3] text-white text-[9px] md:text-[11px] font-bold px-3 py-1 rounded-full uppercase tracking-[0.1em] mb-3">
              智能深度评阅
            </div>
            <h1 className="text-xl md:text-4xl font-extrabold text-[#1d1d1f] tracking-tight leading-tight">
              {questionTitle}
            </h1>
            <p className="text-[#86868b] font-medium text-base md:text-lg mt-2">{paperName}</p>
          </div>

          <div className="p-6 md:p-12 pb-20 md:pb-24 overflow-visible min-h-0">
            <div
              className="report-markdown prose prose-slate max-w-none overflow-visible
              prose-headings:text-[#1d1d1f] prose-headings:break-words
              prose-p:text-[#1d1d1f] prose-p:my-3 prose-p:break-words
              prose-li:text-[#1d1d1f] prose-ul:my-3 prose-ol:my-3 prose-li:my-1
              prose-strong:text-[#1d1d1f] prose-strong:font-bold
              prose-headings:mt-6 prose-headings:mb-3 first:prose-headings:mt-0
              prose-pre:overflow-x-auto prose-pre:max-w-full"
            >
              {content ? (
                modelEssaySplit ? (
                  <>
                    {modelEssaySplit.before && (
                      <ReactMarkdown remarkPlugins={[remarkGfm]}>{modelEssaySplit.before}</ReactMarkdown>
                    )}
                    {modelEssayRows.length > 0 && (
                      <div className="essay-grid-paper not-prose">
                        {modelEssayRows.map((row, rowIndex) => {
                          const chars = Array.from(row).slice(0, 25);
                          return (
                            <div className="essay-grid-row" key={`${rowIndex}-${row}`}>
                              {Array.from({ length: 25 }, (_, colIndex) => (
                                <span className="essay-grid-cell" key={`${rowIndex}-${colIndex}`}>
                                  {chars[colIndex] || ''}
                                </span>
                              ))}
                            </div>
                          );
                        })}
                      </div>
                    )}
                    {modelEssaySplit.after && (
                      <ReactMarkdown remarkPlugins={[remarkGfm]}>{modelEssaySplit.after}</ReactMarkdown>
                    )}
                  </>
                ) : (
                  <ReactMarkdown remarkPlugins={[remarkGfm]}>{content}</ReactMarkdown>
                )
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
