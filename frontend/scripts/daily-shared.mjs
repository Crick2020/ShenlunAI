/**
 * 每日精读预渲染 · 共用工具
 * 纯 Node ESM，无第三方依赖。
 */
import fs from 'node:fs';
import path from 'node:path';

export const SITE_URL = (process.env.SITE_URL || 'https://shenlun.zaoxin.fun').replace(/\/$/, '');
export const RECENT_LIMIT = 30;   // llms.txt 展示篇数
export const MOBILE_KEEP = 30;    // APP 内置 JSON 篇数
export const RECENT_INDEX_LIMIT = 60;

const ALLOWED_TAGS = /^(?:\/?(?:p|strong|em|br|ul|ol|li|blockquote))$/i;

export function escapeHtml(value = '') {
  return String(value)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

/** JSON 里的富文本只允许白名单标签，其余转义为文本（防 LLM 输出注入） */
export function safeRichHtml(value = '') {
  return String(value).replace(/<([^>]+)>/g, (match, inner) => {
    const tag = inner.trim().replace(/\/$/, '').trim();
    return ALLOWED_TAGS.test(tag) ? match : escapeHtml(match);
  });
}

/** 富文本 HTML → Markdown 纯文本（用于 .md 版与 RSS 描述） */
export function htmlToMarkdown(value = '') {
  return String(value)
    .replace(/<strong>(.*?)<\/strong>/gs, '**$1**')
    .replace(/<em>(.*?)<\/em>/gs, '*$1*')
    .replace(/<\/p>\s*<p>/g, '\n\n')
    .replace(/<p>/g, '')
    .replace(/<\/p>/g, '')
    .replace(/<br\s*\/?>/g, '\n')
    .replace(/<[^>]+>/g, '')
    .replace(/&lt;/g, '<')
    .replace(/&gt;/g, '>')
    .replace(/&quot;/g, '"')
    .replace(/&#39;/g, "'")
    .replace(/&amp;/g, '&')
    .trim();
}

export function formatDateCN(date = '') {
  const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(date);
  return m ? `${m[1]} 年 ${Number(m[2])} 月 ${Number(m[3])} 日` : date;
}

export function yearOf(date = '') {
  return (date || '').slice(0, 4);
}

export function articleUrl(slug) {
  return `${SITE_URL}/daily/${slug}.html`;
}

export function markdownUrl(slug) {
  return `${SITE_URL}/daily/${slug}.md`;
}

export function spaUrl(slug) {
  return `${SITE_URL}/?daily=${slug}`;
}

export function rfc822(iso = '') {
  const d = iso ? new Date(iso) : new Date();
  return Number.isNaN(d.getTime()) ? new Date().toUTCString() : d.toUTCString();
}

export function isoDate(iso = '') {
  return (iso || '').slice(0, 10);
}

export function jsonLd(obj) {
  return JSON.stringify(obj, null, 0).replace(/</g, '\\u003c');
}

export function readJson(file, fallback = null) {
  try {
    return JSON.parse(fs.readFileSync(file, 'utf-8'));
  } catch {
    return fallback;
  }
}

/** 读源目录（frontend/public/content/daily），只取 published 且按日期倒序 */
export function loadPublished(sourceDir) {
  const entries = [];
  for (const name of fs.readdirSync(sourceDir)) {
    if (!/^\d{4}-\d{2}-\d{2}(-\d+)?\.json$/.test(name)) continue;
    const doc = readJson(path.join(sourceDir, name));
    if (doc && doc.status === 'published' && doc.slug) entries.push(doc);
  }
  entries.sort((a, b) => {
    if (a.date !== b.date) return b.date.localeCompare(a.date);
    return (a.edition || 1) - (b.edition || 1);
  });
  return entries;
}

export function writeText(file, content) {
  fs.mkdirSync(path.dirname(file), { recursive: true });
  fs.writeFileSync(file, content, 'utf-8');
}

export function xmlEscape(value = '') {
  return String(value)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&apos;');
}

export function truncate(value = '', max = 60) {
  const s = String(value).replace(/\s+/g, ' ').trim();
  return s.length > max ? `${s.slice(0, max)}…` : s;
}
