/**
 * 回归测试：批改报告里的 **加粗** 是否都能被 react-markdown 正确识别。
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

console.log(failed === 0 ? '\n全部通过' : `\n失败 ${failed} 项`);
process.exit(failed === 0 ? 0 : 1);
