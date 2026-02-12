import React, { useState, useEffect } from 'react';
import Navbar from './components/Navbar';
import Home from './pages/Home';
import ExamDetail from './pages/ExamDetail';
import Report from './pages/Report';
import Profile from './pages/Profile';
import PaymentModal from './components/PaymentModal';
import { Paper, User, Question, HistoryRecord, GradingResult } from './types';
import { geminiService } from './services/geminiService';

const App: React.FC = () => {
  const [currentPage, setCurrentPage] = useState<string>('home');
  const [selectedPaper, setSelectedPaper] = useState<Paper | null>(null);
  const [selectedRecord, setSelectedRecord] = useState<HistoryRecord | null>(null);
  const [user, setUser] = useState<User | null>({
    id: 'u-guest',
    nickname: '申论学习者',
    avatar: 'https://picsum.photos/100/100?random=1'
  });
  const [isPaymentModalOpen, setIsPaymentModalOpen] = useState(false);
  const [isGrading, setIsGrading] = useState(false);
  
  // 新增：加载试卷详情的 Loading 状态
  const [isLoadingPaper, setIsLoadingPaper] = useState(false);
  
  const [history, setHistory] = useState<HistoryRecord[]>([]);

  // Current grading context
  const [pendingGrading, setPendingGrading] = useState<{
    question: Question;
    answer: string;
    images?: string[];
  } | null>(null);

  useEffect(() => {
    const savedHistory = localStorage.getItem('history');
    if (savedHistory) setHistory(JSON.parse(savedHistory));
  }, []);

  const handleLogout = () => {
    setUser(null);
    setHistory([]);
    localStorage.removeItem('history');
    setCurrentPage('home');
  };

  // ------------------------------------------------
  // 🚀 核心修改：点击首页卡片时，去后端抓取详细内容
  // ------------------------------------------------
  const handleSelectPaper = async (summaryPaper: Paper) => {
    setIsLoadingPaper(true); // 开启加载动画
    try {
      console.log(`正在从后端获取试卷详情: ${summaryPaper.id}`);
      
      // 发起请求：/api/paper?id=xxx
      const response = await fetch(`https://shenlun-backend.onrender.com/api/paper?id=${summaryPaper.id}`);
      
      if (!response.ok) {
        throw new Error("试卷加载失败，可能是后端没有这个文件");
      }

      const fullPaperData = await response.json();
      console.log("获取成功:", fullPaperData);

      // 把完整的试卷数据存进去
      setSelectedPaper(fullPaperData);
      // 跳转到考试页
      setCurrentPage('exam');

    } catch (error) {
      console.error(error);
      alert(`无法打开试卷：${summaryPaper.name}\n请检查后端 data 文件夹里有没有对应的 JSON 文件。`);
    } finally {
      setIsLoadingPaper(false); // 关闭加载动画
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

      // 兼容后端返回的原始结构，统一整理成前端需要的 GradingResult 结构
      const normalizedResult: GradingResult = {
        score: rawResult?.score ?? 0,
        maxScore: rawResult?.maxScore ?? (pendingGrading.question.maxScore || 100),
        radarData: rawResult?.radarData ?? {
          points: 80,
          logic: 80,
          language: 80,
          format: 80,
        },
        overallEvaluation: rawResult?.overallEvaluation || '（模型未返回总评，已使用占位说明）',
        detailedComments: rawResult?.detailedComments ?? [],
        modelAnswer:
          rawResult?.modelAnswer ||
          // 如果后端按 perQuestion 返回参考答案，这里尝试提取第一题的参考答案
          (() => {
            const perQ = rawResult?.perQuestion;
            if (perQ && typeof perQ === 'object') {
              const firstKey = Object.keys(perQ)[0];
              if (firstKey) {
                const ref = perQ[firstKey]?.referenceAnswer;
                if (typeof ref === 'string') return ref;
              }
            }
            return '（模型暂未提供参考答案，请根据总评与扣分点自行调整作答。）';
          })(),
      };

      const newRecord: HistoryRecord = {
        id: Math.random().toString(36).substr(2, 9),
        paperName: selectedPaper.name,
        questionTitle: pendingGrading.question.title,
        score: normalizedResult.score,
        timestamp: Date.now(),
        result: normalizedResult,
        userAnswer: pendingGrading.answer
      };

      const updatedHistory = [newRecord, ...history];
      setHistory(updatedHistory);
      localStorage.setItem('history', JSON.stringify(updatedHistory));
      
      setSelectedRecord(newRecord);
      setCurrentPage('report');
    } catch (error: any) {
      const msg = error?.message || String(error);
      alert('批改请求失败：' + (msg.includes('状态码') || msg.includes('Failed') ? msg : '请检查网络或后端是否运行（' + msg + '）'));
      console.error(error);
    } finally {
      setIsGrading(false);
      setPendingGrading(null);
    }
  };

  return (
    <div className="min-h-screen bg-gray-50">
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

      <main>
        {currentPage === 'home' && (
          // 这里传入新的 handleSelectPaper 函数
          <Home onSelectPaper={handleSelectPaper} />
        )}
        
        {currentPage === 'exam' && selectedPaper && (
          <ExamDetail paper={selectedPaper} onGrade={startGradingProcess} />
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
          onClose={() => setIsPaymentModalOpen(false)}
          onPay={executeGrading}
        />
      )}

      {/* 批改中的 Loading 动画 */}
      {isGrading && (
        <div className="fixed inset-0 bg-white/90 backdrop-blur-sm z-[200] flex flex-col items-center justify-center">
          <div className="relative w-24 h-24 mb-6">
            <div className="absolute inset-0 border-4 border-blue-200 rounded-full"></div>
            <div className="absolute inset-0 border-4 border-blue-600 rounded-full border-t-transparent animate-spin"></div>
            <div className="absolute inset-0 flex items-center justify-center">
              <i className="fas fa-brain text-blue-600 text-3xl animate-pulse"></i>
            </div>
          </div>
          <h2 className="text-2xl font-bold text-gray-900 mb-2">AI正在深度阅卷中</h2>
          <p className="text-gray-500 animate-pulse text-center px-6">正在连接后端进行批改，请稍候...</p>
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