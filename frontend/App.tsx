import React, { useState, useEffect, useRef } from 'react';
import Navbar from './components/Navbar';
import Home from './pages/Home';
import ExamDetail from './pages/ExamDetail';
import Report from './pages/Report';
import Profile from './pages/Profile';
import PaymentModal from './components/PaymentModal';
import { Paper, User, Question, HistoryRecord, GradingResult } from './types';
import { API_BASE } from './constants';
import { geminiService } from './services/geminiService';
import { track } from './services/analytics';

const LS_PAPERS_LIST = 'shenlun_papers_v1';
const LS_PAPER_DETAIL_PREFIX = 'shenlun_pd_';
const MAX_CACHED_DETAILS = 30;

function readCachedList(): Paper[] {
  try {
    const raw = localStorage.getItem(LS_PAPERS_LIST);
    return raw ? JSON.parse(raw) : [];
  } catch { return []; }
}

function writeCachedList(papers: Paper[]) {
  try { localStorage.setItem(LS_PAPERS_LIST, JSON.stringify(papers)); } catch {}
}

function readCachedDetail(id: string): Paper | null {
  try {
    const raw = localStorage.getItem(LS_PAPER_DETAIL_PREFIX + id);
    return raw ? JSON.parse(raw) : null;
  } catch { return null; }
}

function writeCachedDetail(id: string, paper: Paper) {
  try {
    localStorage.setItem(LS_PAPER_DETAIL_PREFIX + id, JSON.stringify(paper));
    evictOldDetails();
  } catch {}
}

function evictOldDetails() {
  try {
    const keys: string[] = [];
    for (let i = 0; i < localStorage.length; i++) {
      const k = localStorage.key(i);
      if (k?.startsWith(LS_PAPER_DETAIL_PREFIX)) keys.push(k);
    }
    if (keys.length > MAX_CACHED_DETAILS) {
      keys.sort();
      const toRemove = keys.slice(0, keys.length - MAX_CACHED_DETAILS);
      toRemove.forEach(k => localStorage.removeItem(k));
    }
  } catch {}
}

const cachedList = readCachedList();

const App: React.FC = () => {
  const [currentPage, setCurrentPage] = useState<string>('home');
  const [selectedPaper, setSelectedPaper] = useState<Paper | null>(null);
  const [selectedRecord, setSelectedRecord] = useState<HistoryRecord | null>(null);
  const [filters, setFilters] = useState({ type: '公务员', region: '国考' });
  const [user, setUser] = useState<User | null>({
    id: 'u-guest',
    nickname: '申论学习者',
    avatar: 'https://picsum.photos/100/100?random=1'
  });
  const [isPaymentModalOpen, setIsPaymentModalOpen] = useState(false);
  const [isGrading, setIsGrading] = useState(false);
  const [isLoadingPaper, setIsLoadingPaper] = useState(false);
  const [history, setHistory] = useState<HistoryRecord[]>([]);

  const [papers, setPapers] = useState<Paper[]>(cachedList);
  const [isPapersLoading, setIsPapersLoading] = useState(cachedList.length === 0);

  const paperDetailMemCache = useRef<Map<string, Paper>>(new Map());

  const [pendingGrading, setPendingGrading] = useState<{
    question: Question;
    answer: string;
    images?: string[];
  } | null>(null);

  useEffect(() => {
    const savedHistory = localStorage.getItem('history');
    if (savedHistory) setHistory(JSON.parse(savedHistory));
  }, []);

  useEffect(() => {
    fetch(`${API_BASE}/api/list`)
      .then(res => res.json())
      .then(data => {
        const mappedData = data.map((p: any) => ({
          ...p,
          region: p.region === '国家' ? '国考' : p.region
        }));
        setPapers(mappedData);
        setIsPapersLoading(false);
        writeCachedList(mappedData);
      })
      .catch(err => {
        console.error("加载试卷失败:", err);
        setIsPapersLoading(false);
      });
  }, []);

  // 页面浏览埋点
  useEffect(() => {
    const page = currentPage as 'home' | 'exam' | 'report' | 'profile';
    if (['home', 'exam', 'report', 'profile'].includes(currentPage)) {
      track.pageView(page);
    }
  }, [currentPage]);

  const handleLogout = () => {
    setUser(null);
    setHistory([]);
    localStorage.removeItem('history');
    setCurrentPage('home');
  };

  const inflightPrefetches = useRef<Set<string>>(new Set());

  const prefetchPaper = (paperId: string) => {
    if (paperDetailMemCache.current.has(paperId)) return;
    if (inflightPrefetches.current.has(paperId)) return;
    const lsHit = readCachedDetail(paperId);
    if (lsHit) {
      paperDetailMemCache.current.set(paperId, lsHit);
      return;
    }
    inflightPrefetches.current.add(paperId);
    fetch(`${API_BASE}/api/paper?id=${paperId}`)
      .then(res => res.ok ? res.json() : null)
      .then(data => {
        if (data) {
          paperDetailMemCache.current.set(paperId, data);
          writeCachedDetail(paperId, data);
        }
      })
      .catch(() => {})
      .finally(() => inflightPrefetches.current.delete(paperId));
  };

  const handleSelectPaper = async (summaryPaper: Paper) => {
    const memHit = paperDetailMemCache.current.get(summaryPaper.id);
    if (memHit) {
      setSelectedPaper(memHit);
      setCurrentPage('exam');
      return;
    }

    const lsHit = readCachedDetail(summaryPaper.id);
    if (lsHit) {
      paperDetailMemCache.current.set(summaryPaper.id, lsHit);
      setSelectedPaper(lsHit);
      setCurrentPage('exam');
      return;
    }

    setIsLoadingPaper(true);
    try {
      const response = await fetch(`${API_BASE}/api/paper?id=${summaryPaper.id}`);
      if (!response.ok) {
        throw new Error("试卷加载失败，可能是后端没有这个文件");
      }
      const fullPaperData = await response.json();

      paperDetailMemCache.current.set(summaryPaper.id, fullPaperData);
      writeCachedDetail(summaryPaper.id, fullPaperData);

      setSelectedPaper(fullPaperData);
      setCurrentPage('exam');
    } catch (error) {
      console.error(error);
      alert(`无法打开试卷：${summaryPaper.name}\n请检查后端 data 文件夹里有没有对应的 JSON 文件。`);
    } finally {
      setIsLoadingPaper(false);
    }
  };

  const startGradingProcess = (question: Question, answer: string, images?: string[]) => {
    if (!answer.trim() && (!images || images.length === 0)) {
      alert('请先填写您的作答内容或上传答案图片');
      return;
    }
    setPendingGrading({ question, answer, images });
    setIsPaymentModalOpen(true);
  };

  const executeGrading = async () => {
    if (!pendingGrading || !selectedPaper) return;
    
    setIsPaymentModalOpen(false);
    setIsGrading(true);

    try {
      // 这里会调用 geminiService，它已经改成了连接你的 Python 后端
      const rawResult: any = await geminiService.gradeEssay(
        selectedPaper.id,
        selectedPaper.materials,
        pendingGrading.question,
        pendingGrading.answer,
        pendingGrading.images
      );

      // 后端现在直接返回 Markdown 正文（content/modelRawOutput），前端仅展示该内容
      const mainContent = (rawResult?.content ?? rawResult?.modelRawOutput ?? '').trim();
      // 无 Gemini 返回内容（如后端未配置或报错占位）时不进入批改页，避免展示模拟/空白
      if (!mainContent) {
        track.gradingResult(selectedPaper, pendingGrading.question, 'fail', 'no content');
        alert('服务器忙，请稍后再试');
        return;
      }
      const normalizedResult: GradingResult = {
        score: rawResult?.score ?? 0,
        maxScore: rawResult?.maxScore ?? (pendingGrading.question.maxScore || 100),
        radarData: rawResult?.radarData ?? {
          points: 80,
          logic: 80,
          language: 80,
          format: 80,
        },
        overallEvaluation: rawResult?.overallEvaluation || '',
        detailedComments: rawResult?.detailedComments ?? [],
        modelAnswer: rawResult?.modelAnswer ?? '',
        modelRawOutput: mainContent,
        perQuestion: rawResult?.perQuestion,
      };

      const newRecord: HistoryRecord = {
        id: Math.random().toString(36).substr(2, 9),
        paperName: selectedPaper.name,
        questionTitle: pendingGrading.question.title,
        score: normalizedResult.score,
        timestamp: Date.now(),
        result: normalizedResult,
        userAnswer: pendingGrading.answer,
        rawGradingResponse: rawResult,
      };

      const updatedHistory = [newRecord, ...history];
      setHistory(updatedHistory);
      localStorage.setItem('history', JSON.stringify(updatedHistory));
      setSelectedRecord(newRecord);
      track.gradingResult(selectedPaper, pendingGrading.question, 'success');
      setCurrentPage('report');
    } catch (error: any) {
      const msg = error?.message || String(error);
      track.gradingResult(selectedPaper, pendingGrading.question, 'fail', msg);
      alert('服务器忙，请稍后再试');
      console.error(error);
    } finally {
      setIsGrading(false);
      setPendingGrading(null);
    }
  };

  return (
    <div className="min-h-screen bg-gray-50">
      {currentPage !== 'exam' && (
        <Navbar 
          user={user} 
          onLogin={() => {}} 
          onLogout={handleLogout}
          onNavigate={(page) => {
            if (page === 'home') {
              setSelectedPaper(null);
              setSelectedRecord(null);
            }
            setCurrentPage(page);
          }}
        />
      )}

      <main>
        {currentPage === 'home' && (
          <Home onSelectPaper={handleSelectPaper} onPrefetchPaper={prefetchPaper} filters={filters} setFilters={setFilters} papers={papers} isLoading={isPapersLoading} />
        )}
        
        {currentPage === 'exam' && selectedPaper && (
          <ExamDetail paper={selectedPaper} onGrade={startGradingProcess} onBack={() => setCurrentPage('home')} />
        )}

        {currentPage === 'report' && selectedRecord && (
          <Report 
            record={selectedRecord} 
            onBack={() => {
              setSelectedRecord(null);
              setCurrentPage('profile');
            }} 
          />
        )}

        {currentPage === 'profile' && (
          <Profile 
            history={history} 
            onViewRecord={(rec) => {
              setSelectedRecord(rec);
              setCurrentPage('report');
            }} 
          />
        )}
      </main>

      {pendingGrading && (
        <PaymentModal 
          isOpen={isPaymentModalOpen} 
          type={pendingGrading.question.type}
          paperId={selectedPaper?.id}
          onClose={() => setIsPaymentModalOpen(false)}
          onPay={executeGrading}
        />
      )}

      {/* 批改中的 Loading 动画 */}
      {isGrading && (
        <div className="fixed inset-0 bg-white/90 backdrop-blur-sm z-[200] flex flex-col items-center justify-center">
          <div className="book-container mb-8">
            <div className="book">
              <div className="book-spine"></div>
              <div className="book-page book-page-3"></div>
              <div className="book-page book-page-2"></div>
              <div className="book-page book-page-1">
                <div className="book-lines">
                  <div className="book-line"></div>
                  <div className="book-line"></div>
                  <div className="book-line"></div>
                  <div className="book-line"></div>
                  <div className="book-line"></div>
                  <div className="book-line"></div>
                  <div className="book-line"></div>
                </div>
              </div>
            </div>
          </div>
          <h2 className="text-2xl font-bold text-[#1d1d1f] mb-2">正在深度阅卷中</h2>
          <p className="text-[#86868b] text-sm animate-pulse text-center px-6">阅卷老师正在逐段精批您的答卷，请稍候...</p>
        </div>
      )}

      {/* 新增：加载试卷时的 Loading 动画 */}
      {isLoadingPaper && (
        <div className="fixed inset-0 bg-black/20 backdrop-blur-sm z-[200] flex flex-col items-center justify-center">
          <div className="bg-white p-6 rounded-2xl shadow-xl flex flex-col items-center">
            <div className="w-10 h-10 border-4 border-blue-200 border-t-blue-600 rounded-full animate-spin mb-3"></div>
            <p className="text-gray-700 font-bold">正在打开试卷...</p>
          </div>
        </div>
      )}
    </div>
  );
};

export default App;