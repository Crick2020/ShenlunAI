
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
}

export interface HistoryRecord {
  id: string;
  paperName: string;
  questionTitle: string;
  score: number;
  timestamp: number;
  result: GradingResult;
  userAnswer: string;
}

export interface User {
  id: string;
  nickname: string;
  avatar: string;
}
