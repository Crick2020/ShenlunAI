/**
 * 申论题目类型（用于批改历史卡片上的标签）。
 * 后端试卷数据只有 SMALL / ESSAY 两种 type，细分题型由题干文本推断。
 */
import { Question, QuestionType } from '../types';

export type QuestionCategory = '单一题' | '综合分析' | '公文写作' | '大作文';

/** 公文写作（应用文）常见文种 */
const OFFICIAL_DOC_PATTERNS = [
  '讲话稿', '发言稿', '演讲稿', '致辞', '主持词', '讲解稿', '解说词',
  '倡议书', '公开信', '感谢信', '慰问信', '邀请函', '一封信', '书信', '回信', '复信',
  '宣传稿', '新闻稿', '新闻报道', '新闻述评', '短评', '时评', '网评', '编者按', '评论',
  '调研报告', '调研提纲', '工作报告', '工作总结', '考察报告', '情况报告', '总结报告',
  '汇报材料', '汇报提纲', '介绍材料', '发言材料', '参评材料', '推荐材料', '宣传材料',
  '建议书', '提案', '议案', '通知', '通报', '请示', '批复', '意见函', '公函',
  '工作方案', '实施方案', '策划方案', '活动方案', '工作计划',
  '简报', '启事', '招募', '推介', '宣传手册', '展板', '微博', '公众号',
  '提纲', '摘要', '文种',
];

/** 综合分析（谈理解 / 谈看法 / 谈启示 / 评析等） */
const ANALYSIS_PATTERNS = [
  '理解', '认识', '看法', '见解', '评析', '简析', '阐释', '解释', '辨析',
  '启示', '思考', '评价', '比较', '判断', '观点', '感悟', '体会', '想法',
  '如何理解', '怎么理解',
];

/**
 * 公文写作的动词信号（拟写 / 起草 / 撰写…）。
 * 申论里这几个动词几乎只用于公文、应用文类题目，出现即按公文写作处理。
 */
const OFFICIAL_DOC_VERBS = ['拟写', '拟定', '撰写', '起草', '草拟', '代拟', '写作', '写一份', '写一篇'];

function includesAny(text: string, patterns: string[]): boolean {
  return patterns.some((p) => text.includes(p));
}

/**
 * 推断题目类型：大作文 → 公文写作 → 综合分析 → 单一题（兜底）。
 * 顺序很重要：「拟写一篇调研报告提纲」是公文而不是单一题，
 * 「谈谈你的理解」也不能因为出现「分析」就被当成单一题。
 */
export function inferQuestionCategory(question: Pick<Question, 'title' | 'type'> | null | undefined): QuestionCategory {
  if (!question) return '单一题';
  if (question.type === QuestionType.ESSAY) return '大作文';

  const title = (question.title || '').replace(/\s+/g, '');
  if (!title) return '单一题';

  // 自拟题目写文章 → 大作文（个别试卷 type 标错时兜底）
  if (title.includes('写一篇文章') || title.includes('自拟题目') || title.includes('自选角度')) {
    return '大作文';
  }

  if (includesAny(title, OFFICIAL_DOC_VERBS)) return '公文写作';
  if (includesAny(title, OFFICIAL_DOC_PATTERNS)) return '公文写作';
  if (includesAny(title, ANALYSIS_PATTERNS)) return '综合分析';

  // 概括 / 归纳 / 提出对策等，其余小题统一按单一题
  return '单一题';
}

/** 从历史记录里取题目类型：新记录直接读字段，老记录按题干推断 */
export function resolveQuestionCategory(record: {
  questionCategory?: QuestionCategory;
  questionTitle?: string;
}): QuestionCategory {
  if (record.questionCategory) return record.questionCategory;
  return inferQuestionCategory({ title: record.questionTitle || '', type: QuestionType.SMALL });
}

/** 标签配色：用内联色值，避免 Tailwind 按需扫描漏掉动态类名 */
export const QUESTION_CATEGORY_STYLES: Record<QuestionCategory, { backgroundColor: string; color: string }> = {
  单一题: { backgroundColor: '#eef4ff', color: '#0071e3' },
  综合分析: { backgroundColor: '#f3efff', color: '#6b45d6' },
  公文写作: { backgroundColor: '#fff4e5', color: '#b8730a' },
  大作文: { backgroundColor: '#e9f7ef', color: '#1a8a4f' },
};
