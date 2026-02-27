/**
 * 统一埋点层：所有统计上报仅通过本模块，与业务解耦。
 * 支持百度统计（_hmt）和 Umami（自建 fetch 上报，不依赖官方 script 的 404 端点）。
 *
 * 接入说明：
 * - 百度统计：index.html 已内嵌脚本。
 * - Umami：在 .env 中配置 VITE_UMAMI_WEBSITE_ID（必填），可选 VITE_UMAMI_API_URL（默认 https://cloud.umami.is）。
 *   若 Cloud 仍 404，可尝试改为自建实例地址或咨询 Umami 官方当前推荐端点。
 *
 * 如何确认埋点是否发送：
 * - 开发环境：Console 筛选 [analytics] 看日志。
 * - 生产环境：F12 → Network 筛选 umami 或配置的 API 域名。
 */

import type { Paper, Question, HistoryRecord } from '../types';
import { QuestionType } from '../types';

declare global {
  interface Window {
    _hmt?: Array<[string, ...unknown[]]>;
  }
}

const isDev = typeof import.meta !== 'undefined' && (import.meta as any).env?.DEV !== undefined
  ? (import.meta as any).env.DEV
  : (typeof process !== 'undefined' && process.env?.NODE_ENV === 'development');

const UMAMI_WEBSITE_ID = typeof import.meta !== 'undefined' ? (import.meta as any).env?.VITE_UMAMI_WEBSITE_ID : undefined;
const UMAMI_API_URL = (typeof import.meta !== 'undefined' ? (import.meta as any).env?.VITE_UMAMI_API_URL : undefined) || 'https://cloud.umami.is';

/** 向百度统计上报 */
function sendBaidu(eventName: string, action: string, label: string, value?: number) {
  if (typeof window !== 'undefined' && window._hmt) {
    window._hmt.push(['_trackEvent', eventName, action, label, value ?? 0]);
  }
}

/**
 * 使用 fetch 直接向 Umami API 上报，避免官方 script 的默认端点 404。
 * 格式见 https://umami.is/docs/api/sending-stats
 */
function sendUmami(eventName: string, data?: Record<string, unknown>) {
  if (!UMAMI_WEBSITE_ID || typeof window === 'undefined') return;
  const url = `${UMAMI_API_URL.replace(/\/$/, '')}/api/send`;
  const screen = typeof window.screen !== 'undefined' ? `${window.screen.width}x${window.screen.height}` : '';
  const payload = {
    website: UMAMI_WEBSITE_ID,
    name: eventName,
    hostname: window.location.hostname || '',
    url: window.location.pathname || '/',
    title: document.title || '',
    referrer: document.referrer || '',
    language: navigator.language || '',
    screen,
    ...(data && Object.keys(data).length > 0 ? { data } : {}),
  };
  fetch(url, {
    method: 'POST',
    keepalive: true,
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ type: 'event', payload }),
  }).catch(() => {});
}

/**
 * 统一上报入口：同时发送到百度统计和 Umami。
 * 开发环境只打印日志，不发真实请求。
 */
function send(eventName: string, action: string, label: string, value?: number) {
  if (isDev) {
    console.log('[analytics]', eventName, action, label, value ?? '');
    return;
  }
  sendBaidu(eventName, action, label, value);
  sendUmami(eventName, { action, label, ...(value !== undefined && { value }) });
}

function sendParams(eventName: string, params: Record<string, unknown>) {
  if (isDev) {
    console.log('[analytics]', eventName, params);
    return;
  }
  sendBaidu(eventName, 'event', JSON.stringify(params));
  sendUmami(eventName, params);
}

// ── 会话 / 留存辅助 ────────────────────────────────────────────────────────
const LS_FIRST_VISIT  = 'shenlun_first_visit';
const LS_LAST_VISIT   = 'shenlun_last_visit';
const LS_VISIT_COUNT  = 'shenlun_visit_count';

function getToday(): string {
  return new Date().toISOString().slice(0, 10);
}

function daysBetween(a: string, b: string): number {
  return Math.round((new Date(b).getTime() - new Date(a).getTime()) / 86400000);
}

/**
 * 读取并更新 localStorage 中的访问记录。
 * 返回本次会话的关键统计字段，供 userSessionStart 上报。
 */
function computeAndUpdateSession() {
  const today = getToday();
  const firstVisit = localStorage.getItem(LS_FIRST_VISIT);
  const lastVisit  = localStorage.getItem(LS_LAST_VISIT);
  const visitCount = parseInt(localStorage.getItem(LS_VISIT_COUNT) || '0', 10);

  const isNewUser = !firstVisit;
  const isNewDay  = lastVisit !== today;

  const daysSinceFirst = firstVisit ? daysBetween(firstVisit, today) : 0;
  const lastVisitDaysAgo = lastVisit && lastVisit !== today ? daysBetween(lastVisit, today) : 0;
  const newVisitCount = isNewDay ? visitCount + 1 : visitCount;

  if (isNewUser) localStorage.setItem(LS_FIRST_VISIT, today);
  if (isNewDay)  {
    localStorage.setItem(LS_LAST_VISIT, today);
    localStorage.setItem(LS_VISIT_COUNT, String(newVisitCount));
  }

  return { isNewUser, isNewDay, visitCount: newVisitCount, daysSinceFirst, lastVisitDaysAgo };
}
// ──────────────────────────────────────────────────────────────────────────

export const track = {
  /**
   * 用户会话开始（每次打开页面触发）。
   * - is_new_user: 首次访问
   * - is_new_day: 今天首次访问（用于 DAU 统计）
   * - visit_count: 累计访问天数
   * - days_since_first: 距首次访问的天数（留存分析）
   * - last_visit_days_ago: 距上次访问的天数（0 = 当天已访问过）
   */
  userSessionStart() {
    try {
      const { isNewUser, isNewDay, visitCount, daysSinceFirst, lastVisitDaysAgo } =
        computeAndUpdateSession();
      sendParams('user_session_start', {
        is_new_user: isNewUser,
        is_new_day: isNewDay,
        visit_count: visitCount,
        days_since_first: daysSinceFirst,
        last_visit_days_ago: lastVisitDaysAgo,
      });
    } catch {}
  },

  /** 页面浏览：home | exam | report | profile */
  pageView(page: 'home' | 'exam' | 'report' | 'profile') {
    send('page_view', 'view', page);
  },

  /** 首页点击试卷卡片 */
  paperClick(paper: Paper) {
    sendParams('paper_click', {
      paper_id: paper.id,
      paper_name: paper.name,
      exam_type: paper.examType,
      region: paper.region,
      year: paper.year,
    });
  },

  /**
   * 做题页点击「提交并批改」。
   * 新增 question_type（SMALL / ESSAY）和 answer_length（答案字数）。
   */
  paperSubmitClick(paper: Paper, question: Question, answerLength?: number) {
    sendParams('paper_submit_click', {
      paper_id: paper.id,
      paper_name: paper.name,
      question_id: question.id,
      question_title: question.title,
      question_type: question.type,
      answer_length: answerLength ?? 0,
    });
  },

  /**
   * 批改结果：成功或失败，仅接口返回后上报一次。
   * 新增 question_type 以便分开统计小题/大题批改量。
   */
  gradingResult(
    paper: { id: string; name: string },
    question: { id: string; title: string; type?: QuestionType },
    status: 'success' | 'fail',
    error?: string
  ) {
    sendParams('grading_result', {
      paper_id: paper.id,
      paper_name: paper.name,
      question_id: question.id,
      question_type: question.type ?? 'UNKNOWN',
      status,
      ...(error && { error: error.slice(0, 200) }),
    });
  },

  /** 首页筛选变更（含地区 tag 点击） */
  filterChange(filterType: 'type' | 'region', value: string) {
    sendParams('filter_change', { filter_type: filterType, value });
  },

  /** 做题页返回 */
  examBack(paperId: string) {
    sendParams('exam_back', { paper_id: paperId });
  },

  /** 做题页材料/题目 Tab 切换（移动端） */
  examTabSwitch(tab: 'material' | 'question') {
    sendParams('exam_tab_switch', { tab });
  },

  /**
   * 做题页切换题目。
   * question_index 从 0 开始；question_type 区分小题/大题。
   */
  questionSwitch(paperId: string, questionIndex: number, questionType: QuestionType) {
    sendParams('question_switch', {
      paper_id: paperId,
      question_index: questionIndex,
      question_type: questionType,
    });
  },

  /**
   * 用户在某题首次开始作答（输入任意字符时触发一次）。
   * 用于分析「看了但没答」vs「真正作答」的转化漏斗。
   */
  answerStart(paperId: string, questionId: string, questionType: QuestionType) {
    sendParams('answer_start', {
      paper_id: paperId,
      question_id: questionId,
      question_type: questionType,
    });
  },

  /**
   * 做题页点击拍照/上传，或通过粘贴上传图片成功。
   * source: 'button'（点击上传按钮）| 'paste'（粘贴）
   */
  photoUploadClick(paperId: string, questionId: string, source: 'button' | 'paste' = 'button') {
    sendParams('photo_upload_click', { paper_id: paperId, question_id: questionId, source });
  },

  /** 支付弹窗确认去批改 */
  paymentModalConfirm(paperId?: string) {
    if (paperId) sendParams('payment_modal_confirm', { paper_id: paperId });
    else send('payment_modal_confirm', 'click', 'confirm');
  },

  /** 支付弹窗关闭 */
  paymentModalClose(paperId?: string) {
    if (paperId) sendParams('payment_modal_close', { paper_id: paperId });
    else send('payment_modal_close', 'click', 'close');
  },

  /** 报告页返回列表 */
  reportBack() {
    send('report_back', 'click', 'back');
  },

  /** 报告页一键复制 */
  reportCopy() {
    send('report_copy', 'click', 'copy');
  },

  /** 导航点击 */
  navClick(target: 'home' | 'list' | 'history' | 'profile' | 'logout') {
    sendParams('nav_click', { target });
  },

  /** 历史记录点击某条 */
  historyRecordClick(record: HistoryRecord) {
    sendParams('history_record_click', {
      paper_name: record.paperName,
      record_id: record.id,
    });
  },
};
