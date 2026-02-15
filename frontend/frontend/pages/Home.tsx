import React, { useState, useEffect } from 'react';
import { EXAM_TYPES, REGIONS } from '../constants';
import { Paper } from '../types';

interface HomeProps {
  onSelectPaper: (paper: Paper) => void;
}

const Home: React.FC<HomeProps> = ({ onSelectPaper }) => {
  // 1. 新增：用来存后端传来的真试卷数据
  const [papers, setPapers] = useState<Paper[]>([]);
  // 2. 新增：加载状态
  const [isLoading, setIsLoading] = useState(true);

  const [filters, setFilters] = useState({
    type: '公务员',
    region: '全国',
  });
 

  // 3. 去后端抓取试卷列表（带超时，避免 Render 冷启动时一直转圈）
  const [listError, setListError] = useState<string | null>(null);
  useEffect(() => {
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), 28000);

    fetch('https://shenlun-backend.onrender.com/api/list', { signal: controller.signal })
      .then(res => {
        clearTimeout(timeoutId);
        if (!res.ok) throw new Error(`请求失败: ${res.status}`);
        return res.json();
      })
      .then(data => {
        console.log("后端试卷列表:", data);
        setPapers(Array.isArray(data) ? data : []);
        setListError(null);
      })
      .catch(err => {
        clearTimeout(timeoutId);
        console.error("加载试卷失败:", err);
        setPapers([]);
        setListError(err.name === 'AbortError'
          ? '后端响应超时，可能正在唤醒，请稍后刷新页面'
          : '加载试卷列表失败，请检查网络或稍后重试');
      })
      .finally(() => setIsLoading(false));
    return () => {
      clearTimeout(timeoutId);
      controller.abort();
    };
  }, []);

  useEffect(() => {
    if (filters.type === '事业单位' && filters.region === '全国') {
      setFilters(prev => ({ ...prev, region: '北京' }));
    }
  }, [filters.type]);

  // 动态计算：只有后端返回中存在试卷的考试类型/地区才显示
  const examTypesFromPapers = Array.from(new Set(
    papers
      .map(p => p.examType || '')
      .filter(Boolean)
  ));
  const availableExamTypes = examTypesFromPapers.length ? examTypesFromPapers : EXAM_TYPES;

  const regionsFromPapers = Array.from(new Set(
    papers
      .filter(p => (p.examType ? p.examType === filters.type : true))
      .map(p => p.region || '')
      .filter(Boolean)
  ));
  const availableRegions = filters.type === '事业单位'
    ? (regionsFromPapers.length ? regionsFromPapers.filter(r => r !== '全国') : REGIONS.filter(r => r !== '全国'))
    : (regionsFromPapers.length ? regionsFromPapers : REGIONS);

  // 把 "全国" 固定放前面，其他省市按首字拼音顺序排序（使用 localeCompare 对中文进行排序）
  const displayedRegions = (() => {
    const arr = Array.from(new Set(availableRegions));
    const hasNational = arr.includes('全国');
    const rest = arr.filter(r => r !== '全国');
    rest.sort((a, b) => a.localeCompare(b, 'zh'));
    return hasNational ? ['全国', ...rest] : rest;
  })();

  // 如果当前选中的 type/region 在可用列表中不存在，自动切换到第一个可用项
  useEffect(() => {
    if (availableExamTypes.length && !availableExamTypes.includes(filters.type)) {
      setFilters(prev => ({ ...prev, type: availableExamTypes[0] }));
    }
  }, [availableExamTypes]);

  useEffect(() => {
    if (availableRegions.length && !availableRegions.includes(filters.region)) {
      setFilters(prev => ({ ...prev, region: availableRegions[0] }));
    }
  }, [availableRegions]);

  // 4. 修改：不再过滤 MOCK_PAPERS，而是过滤从后端拿到的 papers；同一地区内按年份降序（新年份在前）
  const filteredPapers = papers
    .filter(p => {
      const matchType = p.examType ? p.examType === filters.type : true;
      const matchRegion = p.region ? p.region === filters.region : true;
      return matchType && matchRegion;
    })
    .sort((a, b) => (b.year - a.year));

  return (
    <div className="max-w-7xl mx-auto px-4 md:px-6 py-6 md:py-12">
      {/* Hero Header */}
      <div className="mb-8 md:mb-12 text-center">
        <h1 className="text-2xl md:text-5xl font-extrabold text-[#1d1d1f] mb-2 md:mb-4 tracking-tight leading-tight px-4">
          专业的申论 <span className="text-[#0071e3]">智能批改</span> 平台
        </h1>
        <p className="text-sm md:text-lg text-[#86868b] max-w-2xl mx-auto font-medium leading-relaxed px-6">
          还原真实考试体验，为您提供多维度诊断、解析及范文参考。
        </p>
      </div>

      {/* Filter Section */}
      <div className="max-w-4xl mx-auto mb-8 md:mb-12">
        <div className="bg-white/80 apple-blur border border-black/[0.04] p-4 md:p-6 rounded-3xl md:rounded-[32px] shadow-sm">
          <div className="space-y-4 md:space-y-6">
            
            {/* Exam Type */}
            <div className="flex flex-col md:flex-row md:items-center">
              <div className="shrink-0 mb-2 md:mb-0 md:w-24">
                <span className="text-[11px] font-bold text-[#86868b] uppercase tracking-[0.1em] opacity-70">考试类型</span>
              </div>
              <div className="flex-1">
                <div className="inline-flex bg-[#f5f5f7] p-1 rounded-xl border border-black/[0.02] w-full md:w-auto">
                  {availableExamTypes.map(t => (
                    <button 
                      key={t}
                      onClick={() => setFilters(f => ({ ...f, type: t }))}
                      className={`flex-1 md:flex-none px-4 md:px-6 py-1.5 md:py-2 rounded-lg text-[13px] md:text-[14px] font-semibold transition-all duration-300 whitespace-nowrap ${
                        filters.type === t 
                        ? 'bg-white text-[#1d1d1f] shadow-sm scale-[1.01]' 
                        : 'text-[#86868b] hover:text-[#1d1d1f]'
                      }`}
                    >
                      {t}
                    </button>
                  ))}
                </div>
              </div>
            </div>

            

            <div className="h-px bg-black/[0.03] w-full"></div>

            {/* Region Selector */}
            <div className="flex flex-col md:flex-row md:items-start">
              <div className="shrink-0 mt-1 mb-2 md:mb-0 md:w-24">
                <span className="text-[11px] font-bold text-[#86868b] uppercase tracking-[0.1em] opacity-70">所属地区</span>
              </div>
              <div className="flex-1">
                <div className="flex flex-wrap gap-1.5 md:gap-2">
                  {displayedRegions.map(r => (
                    <button 
                      key={r}
                      onClick={() => setFilters(f => ({ ...f, region: r }))}
                      className={`px-3 md:px-4 py-1.5 rounded-xl text-[12px] md:text-[14px] font-semibold transition-all duration-300 border ${
                        filters.region === r 
                        ? 'bg-[#0071e3] text-white border-[#0071e3] shadow-sm' 
                        : 'bg-white text-[#1d1d1f] border-black/[0.05] hover:border-black/[0.1] hover:bg-[#f5f5f7]'
                      }`}
                    >
                      {r}
                    </button>
                  ))}
                </div>
              </div>
            </div>
            
          </div>
        </div>
      </div>

      {/* 状态显示：加载中 或 试卷列表 */}
      {isLoading ? (
        <div className="text-center py-20 text-gray-400">正在从后端加载试卷...</div>
      ) : listError ? (
        <div className="col-span-full py-16 md:py-24 text-center bg-white/40 rounded-[32px] border border-dashed border-black/10 mx-2">
          <p className="text-[#1d1d1f] font-bold text-base">{listError}</p>
          <button
            onClick={() => window.location.reload()}
            className="mt-4 px-6 py-2 bg-[#0071e3] text-white rounded-full text-sm font-bold"
          >
            刷新页面
          </button>
        </div>
      ) : (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4 md:gap-6">
          {filteredPapers.length > 0 ? (
            filteredPapers.map(paper => (
              <div 
                key={paper.id} 
                className="bg-white rounded-2xl md:rounded-[32px] border border-black/[0.02] apple-card-shadow apple-card-hover overflow-hidden cursor-pointer flex flex-col group p-1"
                onClick={() => onSelectPaper(paper)}
              >
                <div className="p-5 md:p-8 pb-3 flex-1">
                  <div className="flex justify-between items-center mb-3 md:mb-5">
                    <div className="bg-[#f5f5f7] text-[#1d1d1f] text-[9px] font-bold px-2 py-0.5 rounded-full uppercase tracking-wider">{paper.examType}</div>
                    <div className="text-[#86868b] text-[11px] md:text-[12px] font-medium">{paper.year}</div>
                  </div>
                  <h3 className="text-base md:text-xl font-bold text-[#1d1d1f] group-hover:text-[#0071e3] transition-colors duration-500 leading-tight">
                    {paper.name}
                  </h3>
                </div>
                <div className="bg-[#f5f5f7] rounded-xl md:rounded-[24px] m-1 p-3 md:p-4 flex justify-between items-center transition-all duration-700 group-hover:bg-[#0071e3]">
                  <span className="text-[11px] md:text-[12px] font-bold text-[#86868b] group-hover:text-white transition-colors">
                    开始测评
                  </span>
                  <div className="bg-white w-7 h-7 md:w-8 md:h-8 rounded-full flex items-center justify-center text-[#1d1d1f] shadow-sm transition-all duration-500 group-hover:rotate-[-45deg]">
                    <i className="fas fa-arrow-right text-[10px]"></i>
                  </div>
                </div>
              </div>
            ))
          ) : (
            <div className="col-span-full py-16 md:py-24 text-center bg-white/40 rounded-[32px] border border-dashed border-black/10 mx-2">
              <div className="bg-white w-12 h-12 md:w-16 md:h-16 rounded-[20px] md:rounded-[24px] shadow-sm flex items-center justify-center mx-auto mb-4 text-[#d1d1d6]">
                <i className="fas fa-tray text-2xl"></i>
              </div>
              <p className="text-[#1d1d1f] font-bold text-base">暂无匹配试卷</p>
              <p className="text-[#86868b] text-xs md:text-sm mt-1 px-8">请检查后端 data 文件夹是否有对应的 .json 文件</p>
            </div>
          )}
        </div>
      )}
    </div>
  );
};

export default Home;