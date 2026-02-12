import { GradingResult, Question, Material } from "../types";
import { API_BASE } from "../constants";

export class GeminiService {
  constructor() {
    console.log("GeminiService initialized: 准备连接 Python 后端", API_BASE);
  }

  async gradeEssay(
    paperId: string,
    materials: Material[],
    question: Question,
    userAnswer: string,
    images?: string[]
  ): Promise<GradingResult> {
    console.log("正在请求 Python 后端进行批改...", API_BASE);

    try {
      const response = await fetch(`${API_BASE}/api/grade`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
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
          has_images: !!(images && images.length > 0),
        }),
      });

      if (!response.ok) {
        let detail = `状态码: ${response.status}`;
        try {
          const errBody = await response.json();
          if (errBody.detail) detail += " — " + (typeof errBody.detail === "string" ? errBody.detail : JSON.stringify(errBody.detail));
        } catch {
          try {
            detail += " — " + (await response.text()).slice(0, 200);
          } catch {}
        }
        throw new Error(detail);
      }

      const result = await response.json();
      return result as GradingResult;
    } catch (error) {
      console.error("Gemini Grading Error (Frontend):", error);
      throw error;
    }
  }
}

export const geminiService = new GeminiService();