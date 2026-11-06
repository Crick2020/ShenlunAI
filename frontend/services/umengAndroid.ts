import { Capacitor, registerPlugin } from '@capacitor/core';

interface UmengAnalyticsPlugin {
  getPrivacyConsent(): Promise<{ granted: boolean }>;
  grantPrivacyConsent(): Promise<void>;
  track(options: {
    eventId: string;
    params?: Record<string, string | number | boolean>;
  }): Promise<void>;
}

const UmengAnalytics = registerPlugin<UmengAnalyticsPlugin>('UmengAnalytics');
export const UMENG_PRIVACY_CONSENT_KEY = 'aixue_privacy_consent_v1';

type UmengParam = string | number | boolean;

const EVENT_IDS: Record<string, string> = {
  page_view: 'um_page_view',
  paper_click: 'um_paper_click',
  filter_change: 'um_filter_change',
  exam_tab_switch: 'um_exam_tab_switch',
  question_switch: 'um_question_switch',
  answer_start: 'um_answer_start',
  photo_upload_click: 'um_photo_upload',
  paper_submit_click: 'um_grade_submit',
  grading_result: 'um_grade_result',
  history_record_click: 'um_history_open',
  report_copy: 'um_report_copy',
  nav_click: 'um_nav_click',
};

function answerLengthBucket(length: unknown): string {
  const value = Number(length) || 0;
  if (value <= 200) return '0_200';
  if (value <= 500) return '201_500';
  if (value <= 1000) return '501_1000';
  return '1001_plus';
}

function buildParams(
  sourceEvent: string,
  raw: Record<string, unknown>
): Record<string, UmengParam> {
  switch (sourceEvent) {
    case 'page_view':
      return { page: String(raw.label || 'unknown') };
    case 'paper_click':
      return {
        paper_id: String(raw.paper_id || ''),
        exam_type: String(raw.exam_type || ''),
        region: String(raw.region || ''),
        year: Number(raw.year) || 0,
      };
    case 'filter_change':
      return {
        filter_type: String(raw.filter_type || ''),
        filter_value: String(raw.value || ''),
      };
    case 'exam_tab_switch':
      return { tab: String(raw.tab || '') };
    case 'question_switch':
      return {
        question_type: String(raw.question_type || ''),
        question_index: Number(raw.question_index) || 0,
      };
    case 'answer_start':
    case 'grading_result':
      return {
        question_type: String(raw.question_type || ''),
        ...(sourceEvent === 'grading_result' ? { status: String(raw.status || '') } : {}),
      };
    case 'photo_upload_click':
      return { source: String(raw.source || '') };
    case 'paper_submit_click':
      return {
        question_type: String(raw.question_type || ''),
        answer_length_bucket: answerLengthBucket(raw.answer_length),
      };
    case 'nav_click':
      return { target: String(raw.target || '') };
    case 'history_record_click':
    case 'report_copy':
      return {};
    default:
      return {};
  }
}

function cleanParams(params: Record<string, UmengParam>): Record<string, UmengParam> {
  const cleaned: Record<string, UmengParam> = {};
  Object.entries(params).forEach(([key, value]) => {
    if (!/^[a-z][a-z0-9_]{0,63}$/.test(key)) return;
    if (typeof value === 'string') {
      const text = value.trim();
      if (text) cleaned[key] = text.slice(0, 128);
    } else if (typeof value === 'number' || typeof value === 'boolean') {
      cleaned[key] = value;
    }
  });
  return cleaned;
}

export function hasLocalPrivacyConsent(): boolean {
  try {
    return localStorage.getItem(UMENG_PRIVACY_CONSENT_KEY) === 'accepted';
  } catch {
    return false;
  }
}

export async function getPrivacyConsentStatus(): Promise<boolean> {
  if (Capacitor.isNativePlatform() && Capacitor.getPlatform() === 'android') {
    try {
      const result = await UmengAnalytics.getPrivacyConsent();
      if (result.granted) {
        localStorage.setItem(UMENG_PRIVACY_CONSENT_KEY, 'accepted');
        return true;
      }
    } catch (error) {
      console.warn('[umeng] unable to read privacy consent', error);
    }
  }
  return hasLocalPrivacyConsent();
}

export async function grantPrivacyConsent(): Promise<void> {
  localStorage.setItem(UMENG_PRIVACY_CONSENT_KEY, 'accepted');
  if (Capacitor.isNativePlatform() && Capacitor.getPlatform() === 'android') {
    await UmengAnalytics.grantPrivacyConsent();
  }
}

export function trackUmengEvent(
  sourceEvent: string,
  rawParams: Record<string, unknown> = {}
): void {
  if (!Capacitor.isNativePlatform() || Capacitor.getPlatform() !== 'android') return;
  if (!hasLocalPrivacyConsent()) return;

  const eventId = EVENT_IDS[sourceEvent];
  if (!eventId) return;

  const params = cleanParams(buildParams(sourceEvent, rawParams));
  void UmengAnalytics.track({ eventId, params }).catch((error) => {
    console.warn('[umeng] event failed', sourceEvent, error);
  });
}

export const UMENG_EVENT_PLAN = EVENT_IDS;
