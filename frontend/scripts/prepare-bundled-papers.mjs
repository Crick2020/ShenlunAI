import { access, copyFile, mkdir, readFile, readdir, unlink, writeFile } from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const projectRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const sourceCandidates = [
  path.resolve(projectRoot, '..', 'backend', 'data'),
  path.resolve(projectRoot, 'backend', 'data'),
];
const outputDir = path.resolve(projectRoot, 'public', 'papers');

async function findSourceDir() {
  for (const candidate of sourceCandidates) {
    try {
      await access(candidate);
      return candidate;
    } catch {
      // Try the next repository layout.
    }
  }
  throw new Error('Cannot find backend/data. Run this command from the full ShenlunAI repository.');
}

const sourceDir = await findSourceDir();
const entries = await readdir(sourceDir, { withFileTypes: true });
const papers = [];

// 不做整目录删除：一是删除 500+ 文件容易被安全策略拦截，二是覆盖写已经足够，
// 只把「新数据里已经不存在的旧试卷」清理掉即可。
await mkdir(outputDir, { recursive: true });
const written = new Set(['index.json']);

for (const entry of entries) {
  if (!entry.isFile() || !entry.name.endsWith('.json')) continue;

  const sourcePath = path.join(sourceDir, entry.name);
  try {
    const paper = JSON.parse(await readFile(sourcePath, 'utf8'));
    const id = String(paper.id || entry.name.slice(0, -5));
    papers.push({
      id,
      name: paper.name || '未命名试卷',
      year: paper.year || 2024,
      region: paper.region || '全国',
      examType: paper.examType || '公务员',
    });
    const targetName = `${id}.json`;
    written.add(targetName);
    await copyFile(sourcePath, path.join(outputDir, targetName));
  } catch (error) {
    console.warn(`[papers] skipped ${entry.name}: ${error.message}`);
  }
}

const stale = (await readdir(outputDir)).filter((name) => name.endsWith('.json') && !written.has(name));
for (const name of stale) {
  await unlink(path.join(outputDir, name));
}
if (stale.length) console.log(`[papers] 清理已下线试卷 ${stale.length} 份`);

papers.sort((a, b) => {
  const nationalA = a.region === '全国' ? 0 : 1;
  const nationalB = b.region === '全国' ? 0 : 1;
  return nationalA - nationalB
    || String(a.region).localeCompare(String(b.region), 'zh-CN')
    || Number(b.year) - Number(a.year);
});

await writeFile(path.join(outputDir, 'index.json'), JSON.stringify(papers), 'utf8');
console.log(`[papers] bundled ${papers.length} papers into public/papers`);
