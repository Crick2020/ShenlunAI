/**
 * 回归测试：批改报告里的 **加粗** 与公文分段是否能被 react-markdown 正确识别。
 *
 * 背景：CommonMark 判定 `**` 能否开启加粗时，看它前后是否为「空白/标点」。
 * 模型常写 `核心原词是**“农村职业经理人”**`（** 前是汉字、后是中文引号），
 * 这种写法不满足「左/右侧」规则，解析器会把 ** 当普通字符，页面就直接显示星号。
 *
 * 运行：node scripts/check-markdown-bold.mjs
 */
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { build } from 'esbuild';
import { unified } from 'unified';
import remarkParse from 'remark-parse';
import remarkGfm from 'remark-gfm';

const projectRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');

const bundled = await build({
  entryPoints: [path.join(projectRoot, 'utils/normalizeReportMarkdown.ts')],
  bundle: true,
  format: 'esm',
  write: false,
  logLevel: 'error',
});
const mod = await import(
  'data:text/javascript;base64,' + Buffer.from(bundled.outputFiles[0].text).toString('base64')
);
const { normalizeReportMarkdown } = mod;

const CASES = [
  { name: '题干式加粗 + 中文引号', src: '**材料1（乡村CEO）**：核心原词是**“农村职业经理人/乡村CEO”**', expect: 2 },
  { name: '汉字后直接加粗引号内容', src: '核心原词是**“农村职业经理人/乡村CEO”**。', expect: 1 },
  { name: '两个加粗引号并列', src: '**“A”**与**“B”**', expect: 2 },
  { name: '常规加粗不受影响', src: '**重点**：这是常规加粗', expect: 1 },
  { name: '列表项内加粗', src: '- **材料2（乡村工匠）**：原词是**“土专家”“田秀才”**。', expect: 2 },
  { name: '括号紧贴加粗', src: '材料中用了**（乡村CEO）**这一说法', expect: 1 },
  { name: '行内代码里的星号不动', src: '代码 `**不要动我**` 保持原样', expect: 0 },
  { name: '顿号连接多个加粗词', src: '用**“三治融合”**、**“网格化管理”**两个词', expect: 2 },
  { name: '引用行内加粗', src: '> **问题**：**“重形式轻实效”**现象突出。', expect: 2 },
  { name: '表格单元格内加粗', src: '| 立意 | 6/8 | 抓住了**“新职业”**内涵 |', expect: 1 },
];

function analyze(src) {
  const tree = unified().use(remarkParse).use(remarkGfm).parse(src);
  const strongs = [];
  const literalStars = [];
  (function walk(node) {
    if (node.type === 'strong') strongs.push(node.children.map((c) => c.value ?? c.type).join(''));
    if (node.type === 'text' && node.value.includes('**')) literalStars.push(node.value);
    (node.children ?? []).forEach(walk);
  })(tree);
  return { strongs, literalStars };
}

let failed = 0;
for (const { name, src, expect } of CASES) {
  const normalized = normalizeReportMarkdown(src);
  const { strongs, literalStars } = analyze(normalized);
  const ok = literalStars.length === 0 && strongs.length === expect;
  if (!ok) failed += 1;
  console.log(`${ok ? '✓' : '✗'} ${name}`);
  console.log(`   输入: ${src}`);
  console.log(`   归一: ${normalized}`);
  console.log(`   加粗 ${strongs.length}/${expect} 段${literalStars.length ? `；残留字面量 ${JSON.stringify(literalStars)}` : ''}`);
}

// 公文排版回归：模型按「标题/主送/缘由/事项/结语/落款/日期」分段输出时，
// 归一化曾把所有空行删掉，导致 react-markdown 把整篇公文压成一个 <p>。
const officialDoc = [
  '**关于召开村级治理经验现场交流会的请示**',
  '',
  '镇党委：',
  '',
  '我镇在办好民生实事中涌现出一批村级治理典型。为推广先进经验，拟于今年12月下旬召开现场交流会。',
  '',
  '会议拟请单圩村、中关村作经验交流，并组织18个村现场观摩。',
  '',
  '妥否，请批示。',
  '',
  '山阳镇社会治理和社会事业办公室',
  '',
  '×年×月×日',
].join('\n');
const docNorm = normalizeReportMarkdown(officialDoc);
const docTree = unified().use(remarkParse).use(remarkGfm).parse(docNorm);
const docParagraphs = [];
(function walk(node) {
  if (node.type === 'paragraph') docParagraphs.push(node.children.map((c) => c.value ?? c.type).join(''));
  (node.children ?? []).forEach(walk);
})(docTree);
const docOk = docParagraphs.length === 7 && !docNorm.includes('\n\n\n');
if (!docOk) failed += 1;
console.log(`${docOk ? '✓' : '✗'} 公文分段：7 个段落独立渲染（实际 ${docParagraphs.length} 段）`);

const collapsed = normalizeReportMarkdown('第一段。\n\n\n\n第二段。');
const collapseOk = collapsed === '第一段。\n\n第二段。';
if (!collapseOk) failed += 1;
console.log(`${collapseOk ? '✓' : '✗'} 连续空行压缩为一个（${JSON.stringify(collapsed)}）`);

console.log(failed === 0 ? '\n全部通过' : `\n失败 ${failed} 项`);
process.exit(failed === 0 ? 0 : 1);
