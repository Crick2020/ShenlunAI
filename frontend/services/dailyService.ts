/**
 * 每日精读内容读取层。
 *
 * Web：直接读 Vite 复制到 dist/content/daily/ 的 JSON（相对 document.baseURI，兼容子路径部署）。
 * APP：Capacitor 把 dist/ 打进 APK，打包时内置的 JSON 是固定的，所以必须优先在线拉取当天内容，
 *      失败才回退到内置最近 30 篇（mobile 构建会裁剪），否则「每天自动上新」对已安装用户无效。
 *
 * 在线域名可通过 VITE_DAILY_ONLINE_BASE 覆盖（例如国内反代未配置 CORS 时改回 Vercel 原生域名）。
 */
import { Capacitor } from '@capacitor/core';
import type { DailyIndexEntry, DailyLecture } from '../types';

const ONLINE_BASE =
  ((import.meta as any).env?.VITE_DAILY_ONLINE_BASE as string | undefined) ||
  'https://shenlun.zaoxin.fun/content/daily/';

const LOCAL_BASE = new URL('content/daily/', document.baseURI).toString();
const IS_NATIVE = Capacitor.isNativePlatform();
const TIMEOUT_MS = 5000;

let recentCache: DailyIndexEntry[] | null = null;
let allCache: DailyIndexEntry[] | null = null;
const detailCache = new Map<string, DailyLecture>();
let lastOffline = false;

async function fetchJson<T>(url: string, timeoutMs = TIMEOUT_MS): Promise<T | null> {
  const controller = new AbortController();
  const timer = window.setTimeout(() => controller.abort(), timeoutMs);
  try {
    const res = await fetch(url, { signal: controller.signal, cache: 'no-cache' });
    if (!res.ok) return null;
    return (await res.json()) as T;
  } catch {
    return null;
  } finally {
    window.clearTimeout(timer);
  }
}

function publishedOnly(list: DailyIndexEntry[] | null): DailyIndexEntry[] {
  return (list || []).filter((e) => e && e.status === 'published' && e.slug);
}

/** 清单里最新一篇的日期，用于比较「内置」与「线上」谁更新 */
function latestDate(list: DailyIndexEntry[]): string {
  return list.reduce((max, e) => (e.date > max ? e.date : max), '');
}

/** 合并去重：先出现的优先，按日期倒序 */
function mergeEntries(...lists: DailyIndexEntry[][]): DailyIndexEntry[] {
  const map = new Map<string, DailyIndexEntry>();
  for (const list of lists) {
    for (const e of list) if (!map.has(e.slug)) map.set(e.slug, e);
  }
  return [...map.values()].sort(
    (a, b) => b.date.localeCompare(a.date) || (a.edition || 1) - (b.edition || 1),
  );
}

/**
 * 最近 60 篇（首页卡片、日期切换器默认读取）。
 *
 * 原生平台同时读「线上清单」与「APP 内置清单」，取更新的一份为准并合并去重：
 *  - 本地刚打包、线上还没 git push → 内置更新，直接用内置的（测试无需 Git）
 *  - 上线运行几天后 CI 每天上新 → 线上更新，自动切到线上，APP 无需发版
 *  - 断网 → 自动回退内置
 */
export async function getIndex(): Promise<DailyIndexEntry[]> {
  if (recentCache) return recentCache;

  const local = publishedOnly(
    await fetchJson<DailyIndexEntry[]>(`${LOCAL_BASE}index-recent.json`)
    ?? await fetchJson<DailyIndexEntry[]>(`${LOCAL_BASE}index.json`),
  );
  let online: DailyIndexEntry[] = [];
  if (IS_NATIVE) {
    online = publishedOnly(await fetchJson<DailyIndexEntry[]>(`${ONLINE_BASE}index-recent.json`, 3000));
  }
  lastOffline = IS_NATIVE && online.length === 0;

  // 谁更新就以谁为主，另一份作为补充（合并后能同时看到本地新内容与线上历史）
  recentCache = latestDate(online) > latestDate(local)
    ? mergeEntries(online, local)
    : mergeEntries(local, online);
  return recentCache;
}

/** 全量清单（日期切换器「查看更早」时使用） */
export async function getAllIndex(): Promise<DailyIndexEntry[]> {
  if (allCache) return allCache;
  let data: DailyIndexEntry[] | null = null;
  if (IS_NATIVE) {
    data = await fetchJson<DailyIndexEntry[]>(`${ONLINE_BASE}index.json`);
    if (data?.length) lastOffline = false;
  }
  if (!data?.length) {
    data = await fetchJson<DailyIndexEntry[]>(`${LOCAL_BASE}index.json`);
    if (data?.length) lastOffline = IS_NATIVE;
  }
  allCache = publishedOnly(data);
  return allCache;
}

/** 按年分片清单，避免历史很多时一次拉全量 */
export async function getYearIndex(year: string): Promise<DailyIndexEntry[]> {
  if (!/^\d{4}$/.test(year)) return [];
  const file = `index-${year}.json`;
  let data: DailyIndexEntry[] | null = null;
  if (IS_NATIVE) {
    data = await fetchJson<DailyIndexEntry[]>(`${ONLINE_BASE}${file}`);
    if (data?.length) lastOffline = false;
  }
  if (!data?.length) {
    data = await fetchJson<DailyIndexEntry[]>(`${LOCAL_BASE}${file}`);
    if (data?.length) lastOffline = IS_NATIVE;
  }
  return publishedOnly(data);
}

/**
 * 讲义正文：优先读 APP 内置（打包时的内容，不可变且最新），缺失时才在线补。
 * 因此刚重新打包的测试包无需 Git push、无需联网就能看到本地内置的讲义。
 */
export async function getDaily(slug: string): Promise<DailyLecture | null> {
  if (!/^\d{4}-\d{2}-\d{2}(-\d+)?$/.test(slug)) return null;
  const hit = detailCache.get(slug);
  if (hit) return hit;

  let data: DailyLecture | null = await fetchJson<DailyLecture>(`${LOCAL_BASE}${slug}.json`, 3000);
  if (!data && IS_NATIVE) {
    data = await fetchJson<DailyLecture>(`${ONLINE_BASE}${slug}.json`);
    if (data) lastOffline = false;
  }
  if (data && data.status === 'published') {
    detailCache.set(slug, data);
    return data;
  }
  return null;
}

/** 首页精选：优先今天，当天未生成则回退最新一篇 published */
export async function getFeaturedEntry(): Promise<{ entry: DailyIndexEntry | null; isToday: boolean }> {
  const list = await getIndex();
  if (!list.length) return { entry: null, isToday: false };
  const today = beijingToday();
  const todays = list.filter((e) => e.date === today);
  const entry = (todays.length ? todays[todays.length - 1] : list[0]) as DailyIndexEntry;
  return { entry, isToday: entry.date === today };
}

export async function getNeighbors(slug: string): Promise<{
  prev: DailyIndexEntry | null;
  next: DailyIndexEntry | null;
}> {
  const list = await getIndex();
  const i = list.findIndex((e) => e.slug === slug);
  if (i < 0) return { prev: null, next: null };
  // list 按日期倒序：索引更小 = 更新
  return {
    prev: list[i + 1] || null,
    next: list[i - 1] || null,
  };
}

/** 供 UI 标记「离线内容」 */
export function wasOffline(): boolean {
  return lastOffline;
}

export function clearDailyCache(): void {
  recentCache = null;
  allCache = null;
  detailCache.clear();
}

function beijingToday(): string {
  // Date 内部是 UTC 毫秒，+8h 后取 ISO 日期即北京时间日历日
  return new Date(Date.now() + 8 * 60 * 60 * 1000).toISOString().slice(0, 10);
}
