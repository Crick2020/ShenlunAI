/** 材料末尾「工作笔记」等结构化块（与 PDF 表格对应，正文可含 <u> 下划线） */
export type MaterialNotebookSection =
  | {
      type: 'paragraph';
      title: string;
      bodyHtml: string;
    }
  | {
      type: 'remark_table';
      title: string;
      rows: { leftHtml: string; remark?: string }[];
    }
  | {
      type: 'doc_list';
      title: string;
      items: { heading: string; excerptHtml: string; remark?: string }[];
    }
  | {
      type: 'discussion';
      title: string;
      introLines?: string[];
      points: { speaker: string; bodyHtml: string }[];
    };

export interface Material {
  id: string;
  title: string;
  content: string;
  notebookSections?: MaterialNotebookSection[];
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

/* ------------------------------------------------------------------ *
 * 申论每日精读：结构化讲义类型
 * 对应 frontend/public/content/daily/daily.schema.json
 * ------------------------------------------------------------------ */

/** 申论大作文结构骨架：总论点 + 若干分论点 + 结尾 */
export interface DailyStructure {
  score: number;
  essayLike: boolean;
  status: 'standard' | 'acceptable' | 'weak' | 'partial' | 'legacy' | string;
  thesis: { paragraph: number; sentence: string; signals: string[] } | null;
  subTheses: { paragraph: number; sentence: string; signals: string[]; evidence: string[] }[];
  subThesisCount: number;
  conclusion: { paragraph: number; sentence: string; signals: string[]; titleEcho: boolean } | null;
  paragraphCount: number;
  charCount: number;
  outline: string[];
  missing: string[];
  newsReport?: boolean;
  provenance?: string;
  /** 严格分论点判定（选文硬门槛）：段首主张句 + 段内展开 + 语义独立 */
  strict?: {
    pass: boolean;
    score: number;
    subThesisCount: number;
    pattern: string;
    checks: Record<string, boolean | number>;
    rejected?: { paragraph: number; reason: string }[];
    looseSubThesisCount?: number;
  };
  /** 分论点之间的结构关系：并列式 / 递进式 / 辩证式 / 无 */
  pattern?: string;
}

export interface DailyStructureSummary {
  status: string;
  score: number;
  subThesisCount: number;
  hasThesis: boolean;
  hasConclusion: boolean;
  /** 是否通过严格分论点判定 */
  strictPass?: boolean;
  /** 并列式 / 递进式 / 辩证式 */
  pattern?: string;
}

export interface DailySource {
  newspaper: string;
  /** 多官媒来源：媒体名（人民日报 / 光明网 / 中国经济网 …） */
  sourceName?: string;
  /** 展示用来源标签，如「中国经济网·经点热评」 */
  sourceLabel?: string;
  /** 源 id：rmrb / people_opinion / rmlt / gmw / ce / 12371 */
  sourceId?: string;
  paperDate: string;
  page: string;
  column: string;
  author: string;
  originalTitle: string;
  originalUrl: string;
  charCount: number;
  /** 逐字原文段落，质量门禁防幻觉比对的基准 */
  paragraphs: string[];
  /** fetch_sources = 多官媒抓稿原文；migrated-lecture = 人工讲义迁移 */
  provenance?: 'fetch_sources' | 'fetch_rmrb' | 'migrated-lecture';
  /** 由 pipeline/article_structure.py 判定，逐段角色与 segments 一一对应 */
  structure?: DailyStructure;
  /** 回溯选文时的说明：当天无达标文章，实际用了哪一期报纸 */
  selectionNote?: string;
}

export interface DailyOriginal {
  text: string;
  /** 只含 <p>/<strong> 的安全 HTML，重点句已加粗 */
  html: string;
  highlights: string[];
}

export interface DailyConcept {
  term: string;
  boundary: string;
}

export interface DailyAnalysis {
  text: string;
  html: string;
  /** 段落功能，如「中心论点段」「分论点一」「结尾点题」 */
  function: string;
  /** 脚本判定的结构角色：总论点 / 分论点一… / 结尾 / 引子 / 论据 / 过渡分析 / 附注 */
  structureRole?: string;
  devices: string[];
  quotes: string[];
  examples: string[];
  concepts: DailyConcept[];
}

export interface DailySegment {
  index: number;
  original: DailyOriginal;
  analysis: DailyAnalysis;
}

export interface DailyFaq {
  q: string;
  a: string;
}

export interface DailyAccumulation {
  golden: string[];
  standard: string[];
  templates: string[];
  conceptCards: string[];
  metaphorCards: string[];
}

export interface DailyExtras {
  frameworkTable: { index: number; function: string; device: string; role?: string }[];
  accumulation: DailyAccumulation;
  exercise: {
    question: string;
    angles: string[];
    html: string;
  };
}

export interface DailyLecture {
  schemaVersion: number;
  date: string;
  slug: string;
  edition: number;
  title: string;
  keywords: string[];
  source: DailySource;
  summary: string;
  segments: DailySegment[];
  extras: DailyExtras;
  note: string;
  faq: DailyFaq[];
  relatedSlugs: string[];
  status: 'published' | 'draft';
  contentHash: string;
  generatedAt: string;
  model: string;
  promptVersion: string;
  qualityReport?: {
    passed: boolean;
    retries?: number;
    verbatimMatch?: boolean;
    mode?: string;
    checks?: { id: string; ok: boolean; detail?: string }[];
  };
}

/** 清单条目：首页卡片、日期切换器、归档页共用 */
export interface DailyIndexEntry {
  date: string;
  slug: string;
  edition: number;
  title: string;
  keywords: string[];
  summary: string;
  source: {
    newspaper: string;
    paperDate: string;
    page: string;
    column: string;
    author: string;
    charCount: number;
    originalUrl: string;
    sourceName?: string;
    sourceLabel?: string;
    sourceId?: string;
  };
  segmentCount: number;
  /** 精简结构摘要，供首页卡片显示「总论点 + N 分论点 + 结尾」 */
  structure?: DailyStructureSummary;
  status: 'published' | 'draft';
  generatedAt: string;
  contentHash: string;
}
