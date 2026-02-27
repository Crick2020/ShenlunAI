
import React, { useState, useRef, useEffect } from 'react';
import { Paper, Question, Material, QuestionType } from '../types';
import { track } from '../services/analytics';

interface ExamDetailProps {
  paper: Paper;
  onGrade: (question: Question, answer: string, images?: string[]) => void;
  onBack: () => void;
}

const ExamDetail: React.FC<ExamDetailProps> = ({ paper, onGrade, onBack }) => {
  const [activeMaterialIndex, setActiveMaterialIndex] = useState(0);
  const [activeQuestionIndex, setActiveQuestionIndex] = useState(0);
  const [answers, setAnswers] = useState<Record<string, string>>({});
  const [images, setImages] = useState<Record<string, string[]>>({});
  const [uploadingCount, setUploadingCount] = useState(0);
  const [mobileView, setMobileView] = useState<'materials' | 'question'>('materials');
  const fileInputRef = useRef<HTMLInputElement>(null);
  // 记录已触发过 answerStart 的题目 id，避免重复上报
  const answeredQuestions = useRef<Set<string>>(new Set());

  const currentQuestion = paper.questions[activeQuestionIndex];
  const currentAnswer = answers[currentQuestion.id] || '';
  const currentQuestionImages = images[currentQuestion.id] || [];
  const isUploadingImages = uploadingCount > 0;

  // 切题时上报 question_switch（第 0 题首次渲染不上报，属于初始状态）
  const prevQuestionIndexRef = useRef<number | null>(null);
  useEffect(() => {
    if (prevQuestionIndexRef.current === null) {
      prevQuestionIndexRef.current = activeQuestionIndex;
      return;
    }
    if (prevQuestionIndexRef.current !== activeQuestionIndex) {
      track.questionSwitch(paper.id, activeQuestionIndex, currentQuestion.type);
      prevQuestionIndexRef.current = activeQuestionIndex;
    }
  }, [activeQuestionIndex]);

  const handleAnswerChange = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
    const value = e.target.value;
    // 首次有输入时上报 answer_start
    if (value.length > 0 && !answeredQuestions.current.has(currentQuestion.id)) {
      answeredQuestions.current.add(currentQuestion.id);
      track.answerStart(paper.id, currentQuestion.id, currentQuestion.type);
    }
    setAnswers(prev => ({ ...prev, [currentQuestion.id]: value }));
  };

  const handleFileUpload = (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = e.target.files;
    if (files && files.length > 0) {
      setUploadingCount(prev => prev + files.length);
      Array.from(files).forEach(file => {
        const reader = new FileReader();
        reader.onloadend = () => {
          const result = reader.result as string;
          setImages(prev => {
            const currentImages = prev[currentQuestion.id] || [];
            return { ...prev, [currentQuestion.id]: [...currentImages, result] };
          });
          setUploadingCount(prev => prev - 1);
        };
        reader.readAsDataURL(file);
      });
    }
    if (fileInputRef.current) fileInputRef.current.value = '';
  };

  const removeImage = (index: number) => {
    setImages(prev => {
      const currentImages = prev[currentQuestion.id] || [];
      const updated = [...currentImages];
      updated.splice(index, 1);
      return { ...prev, [currentQuestion.id]: updated };
    });
  };

  const handlePaste = (e: React.ClipboardEvent) => {
    const items = e.clipboardData?.items;
    if (!items) return;
    let hasImage = false;
    Array.from(items).forEach(item => {
      if (item.type.startsWith('image/')) {
        hasImage = true;
        const file = item.getAsFile();
        if (file) {
          setUploadingCount(prev => prev + 1);
          const reader = new FileReader();
          reader.onloadend = () => {
            const result = reader.result as string;
            setImages(prev => {
              const currentImages = prev[currentQuestion.id] || [];
              return { ...prev, [currentQuestion.id]: [...currentImages, result] };
            });
            setUploadingCount(prev => prev - 1);
          };
          reader.readAsDataURL(file);
        }
      }
    });
    if (hasImage) {
      track.photoUploadClick(paper.id, currentQuestion.id, 'paste');
      e.preventDefault();
    }
  };

  const handleSubmitClick = () => {
    if (isUploadingImages) {
      alert('图片正在处理中，请稍等 1～2 秒后再提交');
      return;
    }
    track.paperSubmitClick(paper, currentQuestion, currentAnswer.length);
    onGrade(currentQuestion, currentAnswer, currentQuestionImages);
  };

  const toChineseNum = (n: number) => {
    const nums = ['一', '二', '三', '四', '五', '六', '七', '八', '九', '十'];
    return nums[n] || (n + 1).toString();
  };

  const wordCount = currentAnswer.length;

  return (
    <div className="flex flex-col h-screen overflow-hidden bg-white relative">

      {/* Top Header Bar — sticky */}
      <div className="shrink-0 sticky top-0 z-50 border-b border-black/[0.06] bg-white relative flex items-center justify-center h-12 md:h-14 px-4">
        <button
          onClick={() => {
            track.examBack(paper.id);
            onBack();
          }}
          className="absolute left-4 top-1/2 -translate-y-1/2 text-[#1d1d1f] hover:text-[#0071e3] transition-colors p-1"
          aria-label="返回"
        >
          <i className="fas fa-arrow-left text-base md:text-lg"></i>
        </button>
        <h1 className="text-sm md:text-base font-semibold text-[#1d1d1f] truncate max-w-[70%] text-center">
          {paper.name}
        </h1>
      </div>

      {/* Main Content Area */}
      <div className="flex flex-1 overflow-hidden relative">
        
        {/* Left Side: Materials */}
        <div className={`w-full md:w-1/2 flex flex-col bg-[#f5f5f7] overflow-hidden border-r border-black/[0.05] ${mobileView === 'materials' ? 'flex' : 'hidden md:flex'}`}>
          <div className="px-4 md:px-8 pt-4 md:pt-6 pb-2 flex space-x-6 shrink-0 overflow-x-auto no-scrollbar bg-white md:bg-transparent">
            {paper.materials.map((m, idx) => (
              <button
                key={m.id}
                onClick={() => setActiveMaterialIndex(idx)}
                className={`pb-3 text-sm font-semibold whitespace-nowrap transition-all relative ${activeMaterialIndex === idx ? 'text-[#0071e3]' : 'text-[#86868b] hover:text-[#1d1d1f]'}`}
              >
                材料 {idx + 1}
                {activeMaterialIndex === idx && (
                  <div className="absolute bottom-0 left-0 right-0 h-0.5 bg-[#0071e3] rounded-full"></div>
                )}
              </button>
            ))}
          </div>
          <div className="flex-1 overflow-y-auto p-5 md:p-10 lg:p-16 scroll-smooth pb-32 md:pb-16">
            <div className="max-w-2xl mx-auto">
              <h2 className="text-xl md:text-xl font-bold mb-4 md:mb-8 text-[#1d1d1f] tracking-tight">{paper.materials[activeMaterialIndex].title}</h2>
              <div
                className="material-content font-serif-sc text-lg md:text-lg leading-[1.8] md:leading-[2] text-[#1d1d1f] text-justify whitespace-pre-wrap select-text selection:bg-blue-100"
                dangerouslySetInnerHTML={{ __html: paper.materials[activeMaterialIndex].content }}
              />
            </div>
          </div>
        </div>

        {/* Right Side: Questions */}
        <div className={`w-full md:w-1/2 flex flex-col bg-white overflow-hidden ${mobileView === 'question' ? 'flex' : 'hidden md:flex'}`}>
          <div className="flex-1 overflow-y-auto px-4 md:px-10 lg:px-16 py-6 md:py-12 pb-40 md:pb-12 scroll-smooth">
            <div className="max-w-2xl mx-auto space-y-6 md:space-y-10">
              
              {/* Question Navigation */}
              <div className="flex space-x-2 md:space-x-3 overflow-x-auto no-scrollbar py-2">
                {paper.questions.map((_, idx) => (
                  <button
                    key={idx}
                    onClick={() => setActiveQuestionIndex(idx)}
                    className={`px-4 h-8 md:h-9 rounded-full text-[12px] md:text-sm font-bold transition-all shrink-0 whitespace-nowrap ${activeQuestionIndex === idx ? 'bg-[#0071e3] text-white shadow-md' : 'bg-[#f5f5f7] text-[#86868b] hover:bg-[#e8e8ed]'}`}
                  >
                    题目{toChineseNum(idx)}
                  </button>
                ))}
              </div>

              <div className="space-y-4">
                <div className="flex items-start justify-between">
                  <h2 className="text-lg md:text-xl font-bold text-[#1d1d1f] tracking-tight leading-snug">
                    {currentQuestion.title.includes('：') ? currentQuestion.title.split('：')[1] : currentQuestion.title}
                  </h2>
                  <span className="ml-3 bg-blue-50 text-[#0071e3] px-2.5 py-1 rounded-full text-[10px] md:text-xs font-bold shrink-0">
                    {currentQuestion.maxScore}分
                  </span>
                </div>
                
                <div className="bg-[#f5f5f7] rounded-2xl md:rounded-[32px] p-4 md:p-8 border border-black/[0.03]">
                  <p className="text-[12px] font-bold text-[#86868b] uppercase tracking-widest mb-3">作答要求</p>
                  <div className="text-base md:text-[13px] text-[#1d1d1f] leading-relaxed space-y-1.5 md:space-y-2 opacity-90">
                     {currentQuestion.requirements.split('。').filter(r => r.trim()).map((req, i) => (
                       <p key={i} className="flex space-x-2">
                         <span className="text-[#0071e3] font-bold shrink-0">•</span>
                         <span>{req.trim()}</span>
                       </p>
                     ))}
                  </div>
                </div>
              </div>

              {/* Input Area */}
              <div className="space-y-4">
                <div 
                  className="bg-[#fbfbfd] rounded-[28px] md:rounded-[40px] border border-black/[0.05] p-1 shadow-sm transition-all focus-within:ring-2 focus-within:ring-[#0071e3]/20 relative"
                  onPaste={handlePaste}
                >
                  <textarea
                    value={currentAnswer}
                    onChange={handleAnswerChange}
                    placeholder="在此键入您的答案..."
                    className="w-full min-h-[180px] md:min-h-[350px] p-5 md:p-10 bg-transparent text-[#1d1d1f] leading-relaxed outline-none resize-none font-serif-sc text-lg md:text-lg placeholder:text-[#d1d1d6]"
                  />
                  
                  {currentQuestionImages.length > 0 && (
                    <div className="px-5 md:px-10 pb-6">
                      <p className="text-[10px] font-bold text-[#86868b] uppercase tracking-widest mb-3">已上传答题图片 ({currentQuestionImages.length})</p>
                      <div className="flex flex-wrap gap-2 md:gap-4">
                        {currentQuestionImages.map((img, idx) => (
                          <div key={idx} className="relative group/img shrink-0">
                            <img src={img} className="w-16 h-16 md:w-24 md:h-24 object-cover border-2 md:border-4 border-white rounded-xl md:rounded-2xl shadow-md" alt="upload" />
                            <button 
                              onClick={() => removeImage(idx)}
                              className="absolute -top-2 -right-2 bg-[#ff3b30] text-white w-5 h-5 md:w-6 md:h-6 rounded-full shadow-lg flex items-center justify-center text-[10px]"
                            >
                              <i className="fas fa-times"></i>
                            </button>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}

                  <div className="flex flex-col md:flex-row md:items-center justify-between px-5 md:px-10 py-4 md:py-8 border-t border-black/[0.03] space-y-4 md:space-y-0">
                    <div className="text-[12px] font-medium text-[#86868b] flex justify-between md:block">
                      <span>字数统计: <span className={wordCount > currentQuestion.wordLimit ? 'text-red-500 font-bold' : 'text-[#1d1d1f]'}>{wordCount}</span> / {currentQuestion.wordLimit}</span>
                    </div>
                    <div className="hidden md:flex md:items-center space-x-2 md:space-x-4">
                      <button 
                        onClick={() => {
                          track.photoUploadClick(paper.id, currentQuestion.id, 'button');
                          fileInputRef.current?.click();
                        }}
                        className="bg-white border border-black/[0.1] px-4 py-2.5 rounded-xl text-xs font-bold hover:bg-[#f5f5f7] transition-all flex items-center justify-center space-x-2"
                      >
                        <i className="fas fa-camera text-[#0071e3]"></i>
                        <span>拍照上传</span>
                      </button>
                      <button 
                        onClick={handleSubmitClick}
                        disabled={isUploadingImages}
                        className={`bg-[#0071e3] text-white px-6 md:px-10 py-2.5 rounded-full text-xs md:text-sm font-bold shadow-lg shadow-blue-500/20 transition-all ${isUploadingImages ? 'opacity-60 cursor-not-allowed' : 'active:scale-95'}`}
                      >
                        {isUploadingImages ? '图片加载中...' : '提交并批改'}
                      </button>
                    </div>
                  </div>
                </div>

                {/* Mobile Specific Floating Action Group (Red Box Area) */}
                <div className={`md:hidden flex flex-col items-end space-y-4 pt-4 px-2 ${mobileView === 'question' ? 'block' : 'hidden'}`}>
                  <div className="flex items-center space-x-3">
                    <button 
                      onClick={() => {
                        track.photoUploadClick(paper.id, currentQuestion.id, 'button');
                        fileInputRef.current?.click();
                      }}
                      className="w-14 h-14 rounded-full bg-white border border-black/[0.08] shadow-xl flex items-center justify-center text-[#86868b] active:scale-90 transition-transform"
                    >
                      <i className="fas fa-camera text-xl"></i>
                    </button>
                    <button 
                      onClick={handleSubmitClick}
                      disabled={isUploadingImages}
                      className={`w-14 h-14 rounded-full bg-[#0071e3] text-white shadow-xl shadow-blue-500/30 flex items-center justify-center transition-transform ${isUploadingImages ? 'opacity-60 cursor-not-allowed' : 'active:scale-90'}`}
                    >
                      <i className="fas fa-check text-xl"></i>
                    </button>
                  </div>
                </div>

              </div>

            </div>
          </div>
        </div>
      </div>

      {/* Floating Bottom Interaction Bar (Mobile Only) */}
      <div className="md:hidden fixed bottom-6 left-4 right-4 z-[50]">
        <div className="bg-white/80 backdrop-blur-xl border border-black/[0.08] rounded-[24px] shadow-2xl p-2 flex items-center justify-between">
          {/* Segmented Toggle: 材料 | 问题 */}
          <div className="bg-[#f2f2f7] p-1 rounded-full flex relative">
            <div 
              className={`absolute top-1 bottom-1 w-[calc(50%-4px)] bg-white rounded-full shadow-sm transition-all duration-300 ${mobileView === 'materials' ? 'left-1' : 'left-[calc(50%+2px)]'}`}
            ></div>
            <button 
              onClick={() => {
                track.examTabSwitch('material');
                setMobileView('materials');
              }}
              className={`relative z-10 px-4 py-1.5 text-xs font-bold transition-colors w-16 text-center ${mobileView === 'materials' ? 'text-[#1d1d1f]' : 'text-[#86868b]'}`}
            >
              材料
            </button>
            <button 
              onClick={() => {
                track.examTabSwitch('question');
                setMobileView('question');
              }}
              className={`relative z-10 px-4 py-1.5 text-xs font-bold transition-colors w-16 text-center ${mobileView === 'question' ? 'text-[#1d1d1f]' : 'text-[#86868b]'}`}
            >
              问题
            </button>
          </div>

          {/* Quick Status Text */}
          <div 
            onClick={() => {
              track.examTabSwitch('question');
              setMobileView('question');
            }}
            className="flex-1 px-4 text-[#86868b] text-[13px] font-medium truncate text-center"
          >
            {wordCount > 0 ? `已作答 ${wordCount} 字` : '输入答案...'}
          </div>
          
          <div className="w-8 shrink-0"></div> {/* Spacer to balance the bar */}
        </div>
      </div>

      {/* Actual File Input for Camera */}
      <input type="file" ref={fileInputRef} onChange={handleFileUpload} className="hidden" accept="image/*" multiple />
    </div>
  );
};

export default ExamDetail;
