
import { Paper, QuestionType } from './types';

/** 后端 API 根地址。本地开发时在 frontend 目录创建 .env.development 并设置 VITE_API_BASE=http://localhost:8000 */
export const API_BASE = (typeof import.meta !== 'undefined' && (import.meta as any).env?.VITE_API_BASE) || 'https://shenlun-backend.onrender.com';

export const EXAM_TYPES = ['公务员', '事业单位'];
export const REGIONS = ['全国', '北京', '浙江', '广东', '山东', '江苏', '四川'];
export const YEARS = [2025, 2024, 2023, 2022, 2021];

export const MOCK_PAPERS: Paper[] = [
  {
    id: 'p1',
    name: '2024年浙江省公务员录用考试《申论》A卷',
    examType: '公务员',
    region: '浙江',
    year: 2024,
    materials: [
      {
        id: 'm1',
        title: '资料1：共同富裕的浙江探索',
        content: '浙江省作为高质量发展建设共同富裕示范区，深入贯彻新发展理念。近年来，通过“千村示范、万村整治”工程，城乡差距进一步缩小。资料显示，2023年浙江农村居民人均可支配收入增速高于城镇。各级政府通过精准施策，大力发展山区海岛县特色产业，实现了区域协调发展。共同富裕不仅是物质的充裕，更是精神的富有。'
      },
      {
        id: 'm2',
        title: '资料2：数字经济与社会治理',
        content: '数字浙江建设进入新阶段。通过“城市大脑”，基层治理效率提升了30%以上。某市推行的“一屏观全城”，实现了政务服务的高效闭环。然而，在数字化转型过程中，也存在“数字鸿沟”现象，部分老年人对智能设备操作不便。如何在技术进步中保持人文关怀，是当前面临的课题。'
      },
      {
        id: 'm3',
        title: '资料3：文化强省建设',
        content: '深入挖掘“万年上山”、“五千年良渚”等文化名片。浙江文化产业增加值占GDP比重持续上升。文化不仅是产业，更是软实力。通过实施“文化惠民”工程，公共图书馆 and 文化站实现了基层全覆盖。'
      }
    ],
    questions: [
      {
        id: 'q1',
        title: '题目一：根据“给定资料1”，概括浙江省在推动共同富裕方面的经验。',
        requirements: '要求：全面、准确、条理清晰。不超过200字。',
        maxScore: 15,
        wordLimit: 200,
        type: QuestionType.SMALL
      },
      {
        id: 'q2',
        title: '题目二：根据“给定资料2”，分析数字化治理面临的挑战及应对策略。',
        requirements: '要求：分析透彻，建议可行。不超过300字。',
        maxScore: 20,
        wordLimit: 300,
        type: QuestionType.SMALL
      },
      {
        id: 'q3',
        title: '题目三：参考“给定资料”，以“共富路上的文化担当”为题，写一篇议论文。',
        requirements: '要求：观点明确，论证充分，语言流畅。总字数1000-1200字。',
        maxScore: 40,
        wordLimit: 1200,
        type: QuestionType.ESSAY
      }
    ]
  },
  {
    id: 'p2',
    name: '2024年国考公务员《申论》副省级',
    examType: '公务员',
    region: '全国',
    year: 2024,
    materials: [
      { id: 'm1', title: '资料1：科技创新与自立自强', content: '当前，我国正处于科技飞速发展的关键期...' },
      { id: 'm2', title: '资料2：青年人才的时代使命', content: '一代人有一代人的长征，青年一代应当...' }
    ],
    questions: [
      {
        id: 'q1',
        title: '题目一：请概括我国当前科技创新的主要成就。',
        requirements: '不超过150字。',
        maxScore: 10,
        wordLimit: 150,
        type: QuestionType.SMALL
      }
    ]
  }
];
