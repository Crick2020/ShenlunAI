import { GradingResult, Question, Material } from "../types";
import { API_BASE } from "../constants";

export class GeminiService {
  
  constructor() {
    // 之前报错就是因为这里在检查 API Key
    // 现在我们要调用 Python 后端，所以这里什么都不用做，直接通过！
    console.log("GeminiService initialized: 准备连接 Python 后端");
  }

  async gradeEssay(
    paperId: string,
    materials: Material[],
    question: Question,
    userAnswer: string,
    images?: string[] 
  ): Promise<GradingResult> {
    
    console.log("正在请求 Python 后端进行批改...");

    try {
      const response = await fetch(`${API_BASE}/api/grade`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          paperId,
          materials,
          question: {
            id: question.id,
            type: question.type,
            title: question.title,
            requirements: question.requirements,
            maxScore: question.maxScore,
            materialIds: question.materialIds,
          },
          answers: { [question.id]: userAnswer },
          user_answer: userAnswer,
          question_id: question.id,
          has_images: images && images.length > 0,
        })
      });

      // 检查后端是否正常活着
      if (!response.ok) {
        throw new Error(`连接后端失败 (状态码: ${response.status})。请确认 main.py 是否正在运行！`);
      }

      // 拿到 Python 批改完的结果
      const result = await response.json();
      
      return result as GradingResult;

    } catch (error) {
      console.error("Gemini Grading Error (Frontend):", error);
      // 向外抛出错误，让界面能弹出提示
      throw error;
    }
  }
}

export const geminiService = new GeminiService();