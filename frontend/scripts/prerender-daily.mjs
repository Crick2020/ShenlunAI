/**
 * 每日精读 · 构建期预渲染
 *
 * - Web 构建：读 frontend/public/content/daily/*.json，生成独立静态 HTML/MD、
 *   按年归档、sitemap 索引与分片、RSS、llms.txt/llms-full.txt、robots.txt
 * - mobile 构建：跳过全部静态产物，并裁掉 dist/content/daily/ 中 30 篇之外的 JSON，
 *   避免几千篇内容把 APK 撑爆
 *
 * 既作为 Vite 插件（closeBundle 自动执行），也可 CLI 独立运行：
 *   node scripts/prerender-daily.mjs
 */
import fs from 'node:fs';
import crypto from 'node:crypto';
import path from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';

import {
  SITE_URL, RECENT_LIMIT, MOBILE_KEEP, RECENT_INDEX_LIMIT,
  articleUrl, markdownUrl, escapeHtml, xmlEscape, rfc822, isoDate,
  yearOf, loadPublished, readJson, writeText, truncate,
} from './daily-shared.mjs';
import {
  renderArticleHtml, renderArticleMarkdown,
  renderArchiveHtml, renderYearArchiveHtml,
} from './daily-template.mjs';

const SCRIPT_DIR = path.dirname(fileURLToPath(import.meta.url));

function listToIndexEntry(doc) {
  const src = doc.source || {};
  return {
    date: doc.date, slug: doc.slug, edition: doc.edition || 1,
    title: doc.title, keywords: doc.keywords || [], summary: doc.summary || '',
    source: {
      newspaper: src.newspaper || '人民日报', paperDate: src.paperDate || doc.date,
      page: src.page || '', column: src.column || '', author: src.author || '',
      charCount: src.charCount || 0, originalUrl: src.originalUrl || '',
      sourceName: src.sourceName || src.newspaper || '人民日报',
      sourceLabel: src.sourceLabel || '', sourceId: src.sourceId || 'rmrb',
    },
    segmentCount: (doc.segments || []).length,
    structure: (() => {
      const s = (doc.source || {}).structure || {};
      return {
        status: s.status || 'unknown', score: s.score || 0,
        subThesisCount: s.subThesisCount || 0,
        hasThesis: !!s.thesis, hasConclusion: !!s.conclusion,
        strictPass: !!(s.strict && s.strict.pass), pattern: s.pattern || '无',
      };
    })(),
    status: doc.status, generatedAt: doc.generatedAt || '', contentHash: doc.contentHash || '',
  };
}

/** 模板与样式也纳入 hash：只按内容 hash 缓存会导致改了模板却不重建静态页 */
function templateHash(css) {
  const tpl = fs.readFileSync(new URL('./daily-template.mjs', import.meta.url));
  return crypto.createHash('sha1').update(tpl).update(css).digest('hex').slice(0, 12);
}

function dailyMarker(doc, tplHash) {
  return `<!-- daily-hash: ${doc.contentHash || 'none'}-${tplHash} -->`;
}

function injectCssAndMarker(html, css, doc, tplHash) {
  return html
    .replaceAll('__DAILY_CSS__', () => css)
    .replace('<head>', `<head>\n${dailyMarker(doc, tplHash)}`);
}

function buildArticleFiles(docs, distDir, css) {
  const tplHash = templateHash(css);
  const entries = docs.map(listToIndexEntry);
  const bySlug = new Map(entries.map((e) => [e.slug, e]));
  const dailyDir = path.join(distDir, 'daily');
  let written = 0;
  let skipped = 0;

  for (let i = 0; i < docs.length; i++) {
    const doc = docs[i];
    // entries 按日期倒序：索引更小 = 更新
    const prev = entries[i + 1] || null;
    const next = entries[i - 1] || null;
    const html = injectCssAndMarker(
      renderArticleHtml(doc, { allEntries: entries, prev, next }),
      css, doc, tplHash,
    );
    const htmlFile = path.join(dailyDir, `${doc.slug}.html`);
    const marker = dailyMarker(doc, tplHash);
    if (fs.existsSync(htmlFile) && fs.readFileSync(htmlFile, 'utf-8').includes(marker)) {
      skipped++;
    } else {
      writeText(htmlFile, html);
      written++;
    }
    writeText(path.join(dailyDir, `${doc.slug}.md`), renderArticleMarkdown(doc));
  }
  return { written, skipped, bySlug };
}

function buildArchives(docs, distDir, css) {
  const entries = docs.map(listToIndexEntry);
  const years = [...new Set(entries.map((e) => yearOf(e.date)).filter(Boolean))].sort().reverse();
  writeText(
    path.join(distDir, 'daily', 'index.html'),
    renderArchiveHtml(entries, years).replaceAll('__DAILY_CSS__', () => css),
  );
  for (const year of years) {
    const yearEntries = entries.filter((e) => yearOf(e.date) === year);
    writeText(
      path.join(distDir, 'daily', 'archive', `${year}.html`),
      renderYearArchiveHtml(year, yearEntries).replaceAll('__DAILY_CSS__', () => css),
    );
  }
  return { entries, years };
}

function buildSitemaps(entries, years, distDir) {
  const now = isoDate(entries[0]?.generatedAt) || new Date().toISOString().slice(0, 10);
  const staticUrls = [
    { loc: `${SITE_URL}/`, lastmod: now, changefreq: 'daily', priority: '1.0' },
    { loc: `${SITE_URL}/daily/`, lastmod: now, changefreq: 'daily', priority: '0.9' },
    ...years.map((y) => ({
      loc: `${SITE_URL}/daily/archive/${y}.html`, lastmod: now,
      changefreq: 'weekly', priority: '0.6',
    })),
  ];
  const urlset = (urls) => `<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
${urls.map((u) => `  <url><loc>${xmlEscape(u.loc)}</loc><lastmod>${u.lastmod}</lastmod><changefreq>${u.changefreq}</changefreq><priority>${u.priority}</priority></url>`).join('\n')}
</urlset>
`;
  writeText(path.join(distDir, 'sitemap-static.xml'), urlset(staticUrls));

  for (const year of years) {
    const urls = entries.filter((e) => yearOf(e.date) === year).map((e) => ({
      loc: articleUrl(e.slug),
      lastmod: isoDate(e.generatedAt) || e.date,
      changefreq: 'weekly',
      priority: '0.8',
    }));
    writeText(path.join(distDir, `sitemap-daily-${year}.xml`), urlset(urls));
  }

  const index = `<?xml version="1.0" encoding="UTF-8"?>
<sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <sitemap><loc>${SITE_URL}/sitemap-static.xml</loc><lastmod>${now}</lastmod></sitemap>
${years.map((y) => `  <sitemap><loc>${SITE_URL}/sitemap-daily-${y}.xml</loc><lastmod>${now}</lastmod></sitemap>`).join('\n')}
</sitemapindex>
`;
  writeText(path.join(distDir, 'sitemap.xml'), index);
}

function buildRss(entries, distDir) {
  const items = entries.slice(0, 20).map((e) => `  <item>
    <title>${xmlEscape(`《${e.title}》申论每日精读`)}</title>
    <link>${xmlEscape(articleUrl(e.slug))}</link>
    <guid isPermaLink="true">${xmlEscape(articleUrl(e.slug))}</guid>
    <pubDate>${rfc822(e.generatedAt || `${e.date}T08:20:00+08:00`)}</pubDate>
    <description>${xmlEscape(`${e.summary} 关键词：${(e.keywords || []).join('、')}`)}</description>
    <category>申论每日精读</category>
  </item>`).join('\n');
  writeText(path.join(distDir, 'rss.xml'), `<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:atom="http://www.w3.org/2005/Atom">
<channel>
  <title>爱学申论 · 申论每日精读</title>
  <link>${SITE_URL}/daily/</link>
  <description>每天从人民日报等官媒选一篇申论大作文范文（总论点 + 严格分论点 + 结尾）逐段精讲：原文 + 老师解析 + 金句积累 + 迁移练习。</description>
  <language>zh-CN</language>
  <lastBuildDate>${rfc822(entries[0]?.generatedAt)}</lastBuildDate>
  <atom:link href="${SITE_URL}/rss.xml" rel="self" type="application/rss+xml" />
${items}
</channel>
</rss>
`);
}

function buildLlms(entries, years, distDir) {
  const header = `# 爱学申论 · 申论每日精读

> 每天从人民日报、人民网、人民论坛网、光明网、中国经济网、共产党员网等官媒评论栏目，
> 选一篇具备「明确总论点 + 若干严格分论点 + 结尾」的申论大作文范文，产出「原文 + 老师逐段解析」讲义：
> 段落功能、论证方式、金句标准表述、举一反三例句、考点关联与迁移练习。
> 全部内容公开可抓取，原文均回链原刊，仅供学习交流使用。
> 站点：${SITE_URL} ｜ 归档：${SITE_URL}/daily/

## 最近精读

`;
  let body = '';
  let count = 0;
  for (const e of entries.slice(0, RECENT_LIMIT)) {
    const line = `- [《${e.title}》(${e.date})](${articleUrl(e.slug)})：${truncate(e.summary, 48)}｜关键词：${(e.keywords || []).slice(0, 3).join('、')}\n`;
    if ((header + body + line).length > 1800) break;
    body += line;
    count++;
  }
  const footer = `
## 按年归档

${years.map((y) => `- [${y} 年全部精读](${SITE_URL}/daily/archive/${y}.html)`).join('\n')}

## 其他资源

- [完整清单（全量）](${SITE_URL}/llms-full.txt)
- [RSS 订阅](${SITE_URL}/rss.xml)
- [Sitemap](${SITE_URL}/sitemap.xml)
- [首页 / 申论智能批改](${SITE_URL}/)
`;
  writeText(path.join(distDir, 'llms.txt'), header + body + footer);

  const full = `# 爱学申论 · 申论每日精读全量清单（共 ${entries.length} 篇）\n\n` +
    entries.map((e) => `- [《${e.title}》(${e.date})](${articleUrl(e.slug)})｜${(e.keywords || []).join('、')}｜[纯文本版](${markdownUrl(e.slug)})`).join('\n') + '\n';
  writeText(path.join(distDir, 'llms-full.txt'), full);
  return { llmsChars: (header + body + footer).length, llmsItems: count };
}

function buildRobots(distDir) {
  writeText(path.join(distDir, 'robots.txt'), `User-agent: *
Allow: /
Allow: /daily/

Sitemap: ${SITE_URL}/sitemap.xml
# llms.txt: ${SITE_URL}/llms.txt
# RSS: ${SITE_URL}/rss.xml
`);
}

/** mobile 构建：裁掉 30 篇之外的内置 JSON，避免 APK 随天数线性膨胀 */
function pruneForMobile(distDir, docs) {
  const contentDir = path.join(distDir, 'content', 'daily');
  if (!fs.existsSync(contentDir)) return { pruned: 0 };
  const keep = new Set(docs.slice(0, MOBILE_KEEP).map((d) => d.slug));
  let pruned = 0;
  for (const name of fs.readdirSync(contentDir)) {
    const m = /^(\d{4}-\d{2}-\d{2}(-\d+)?)\.json$/.exec(name);
    if (m && !keep.has(m[1])) {
      fs.rmSync(path.join(contentDir, name));
      pruned++;
    }
    if (/^index-\d{4}\.json$/.test(name)) {
      fs.rmSync(path.join(contentDir, name));
      pruned++;
    }
  }
  const recent = docs.slice(0, RECENT_INDEX_LIMIT).map(listToIndexEntry);
  writeText(path.join(contentDir, 'index.json'), JSON.stringify(recent, null, 2) + '\n');
  writeText(path.join(contentDir, 'index-recent.json'), JSON.stringify(recent, null, 2) + '\n');
  return { pruned };
}

export function runPrerender({ root, outDir = 'dist', mode = 'production', base = '/' } = {}) {
  const frontendRoot = path.resolve(root || path.resolve(SCRIPT_DIR, '..'));
  const sourceDir = path.join(frontendRoot, 'public', 'content', 'daily');
  const distDir = path.resolve(frontendRoot, outDir);
  if (!fs.existsSync(sourceDir)) {
    console.warn('[daily] 未找到内容目录，跳过预渲染:', sourceDir);
    return;
  }
  const docs = loadPublished(sourceDir);
  const isMobile = mode === 'mobile' || base === './' || base === '.';
  if (isMobile) {
    const result = pruneForMobile(distDir, docs);
    console.log(`[daily] mobile 模式：跳过静态页，内置 JSON 保留 ${Math.min(docs.length, MOBILE_KEEP)} 篇，清理 ${result.pruned} 个文件`);
    return;
  }
  if (!docs.length) {
    console.warn('[daily] 没有已发布的讲义，跳过静态页生成');
    return;
  }

  const css = fs.readFileSync(path.join(frontendRoot, 'daily-style.css'), 'utf-8');
  const articleResult = buildArticleFiles(docs, distDir, css);
  const { entries, years } = buildArchives(docs, distDir, css);
  buildSitemaps(entries, years, distDir);
  buildRss(entries, distDir);
  const llms = buildLlms(entries, years, distDir);
  buildRobots(distDir);

  console.log(
    `[daily] 预渲染完成：${docs.length} 篇（新建 ${articleResult.written} / 复用 ${articleResult.skipped}）、` +
    `${years.length} 个年份归档、sitemap ${years.length + 1} 个分片、llms.txt ${llms.llmsChars} 字符`,
  );
}

/** Vite 插件：Web 构建时自动生成，mobile 构建时自动裁剪 */
export function dailyPrerender() {
  let resolved;
  return {
    name: 'shenlun-daily-prerender',
    apply: 'build',
    configResolved(config) {
      resolved = config;
    },
    closeBundle() {
      runPrerender({
        root: resolved.root,
        outDir: resolved.build.outDir,
        mode: resolved.mode,
        base: resolved.base,
      });
    },
  };
}

const isCli = process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href;
if (isCli) {
  runPrerender({ root: path.resolve(SCRIPT_DIR, '..'), outDir: 'dist', mode: 'production', base: '/' });
}
