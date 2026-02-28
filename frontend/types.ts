
export interface Material {
  id: string;
  title: string;
  content: string;
}

export enum QuestionType {
  SMALL = 'SMALL',
  ESSAY = 'ESSAY'
}

export interface Question {
  id: string;
  title: string;
  requirements: string;
  maxScore: number;
  wordLimit: number;
  type: QuestionType;
  /** 小题关联的材料 id 列表，仅提交这些材料给批改接口 */
  materialIds?: string[];
}

export interface Paper {
  id: string;
  name: string;
  examType: string;
  region: string;
  year: number;
  materials: Material[];
  questions: Question[];
}

export interface GradingResult {
  score: number;
  maxScore: number;
  radarData: {
    points: number;
    logic: number;
    language: number;
    format: number;
  };
  overallEvaluation: string;
  detailedComments: {
    originalText: string;
    comment: string;
    type: 'positive' | 'negative';
  }[];
  modelAnswer: string;
  /** 原始返回全文（用于批改结果页完整展示） */
  modelRawOutput?: string;
  /** 每题详情（后端 perQuestion） */
  perQuestion?: Record<string, any>;
}

export interface HistoryRecord {
  id: string;
  paperName: string;
  questionTitle: string;
  score: number;
  timestamp: number;
  result: GradingResult;
  userAnswer: string;
  /** 后端 /api/grade 的完整响应（用于完整返回展示） */
  rawGradingResponse?: any;
}

export interface User {
  id: string;
  nickname: string;
  avatar: string;
}
