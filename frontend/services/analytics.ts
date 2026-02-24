/**
 * 统一埋点层：所有统计上报仅通过本模块，与业务解耦。
 * 支持百度统计 _hmt；开发环境仅 log 不上报。
 * 接入说明：在 index.html 中引入百度统计 hm.js（将 YOUR_BAIDU_HM_ID 替换为实际站点 ID）。
 */

import type { Paper, Question, HistoryRecord } from '../types';

declare global {
  interface Window {
    _hmt?: Array<[string, ...unknown[]]>;
  }
}

const isDev = typeof import.meta !== 'undefined' && (import.meta as any).env?.DEV !== undefined
  ? (import.meta as any).env.DEV
  : (typeof process !== 'undefined' && process.env?.NODE_ENV === 'development');

function send(eventName: string, action: string, label: string, value?: number) {
  if (isDev) {
    console.log('[analytics]', eventName, action, label, value ?? '');
    return;
  }
  if (typeof window !== 'undefined' && window._hmt) {
    window._hmt.push(['_trackEvent', eventName, action, label, value ?? 0]);
  }
}

function sendParams(eventName: string, params: Record<string, unknown>) {
  const label = JSON.stringify(params);
  send(eventName, 'event', label);
}

export const track = {
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

  /** 做题页点击「提交并批改」 */
  paperSubmitClick(paper: Paper, question: Question) {
    sendParams('paper_submit_click', {
      paper_id: paper.id,
      paper_name: paper.name,
      question_id: question.id,
      question_title: question.title,
    });
  },

  /** 批改结果：成功或失败，仅接口返回后上报一次 */
  gradingResult(
    paper: { id: string; name: string },
    question: { id: string; title: string },
    status: 'success' | 'fail',
    error?: string
  ) {
    sendParams('grading_result', {
      paper_id: paper.id,
      paper_name: paper.name,
      question_id: question.id,
      status,
      ...(error && { error: error.slice(0, 200) }),
    });
  },

  /** 首页筛选变更 */
  filterChange(filterType: 'type' | 'region', value: string) {
    sendParams('filter_change', { filter_type: filterType, value });
  },

  /** 做题页返回 */
  examBack(paperId: string) {
    sendParams('exam_back', { paper_id: paperId });
  },

  /** 做题页材料/题目 Tab 切换 */
  examTabSwitch(tab: 'material' | 'question') {
    sendParams('exam_tab_switch', { tab });
  },

  /** 做题页点击拍照/上传 */
  photoUploadClick(paperId: string, questionId: string) {
    sendParams('photo_upload_click', { paper_id: paperId, question_id: questionId });
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
