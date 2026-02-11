import { GradingResult, Question, Material } from "../types";

// 这里的 GoogleGenAI 引用被我注释掉了，因为我们不再需要在前端直接用它
// import { GoogleGenAI, Type, GenerateContentResponse } from "@google/genai";

export class GeminiService {
  
  constructor() {
    // 之前报错就是因为这里在检查 API Key
    // 现在我们要调用 Python 后端，所以这里什么都不用做，直接通过！
    console.log("GeminiService initialized: 准备连接 Python 后端");
  }

  async gradeEssay(
    materials: Material[],
    question: Question,
    userAnswer: string,
    images?: string[] 
  ): Promise<GradingResult> {
    
    console.log("正在请求 Python 后端进行批改...");

    try {
      // ---------------------------------------------------------
      // 核心修改：这里不再直接找 Google，而是找你部署在 Render 上的 Python 后端
      // ---------------------------------------------------------
      
      const response = await fetch('https://shenlun-backend.onrender.com/api/grade', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        // 把试卷题目、用户写的答案打包发给 Python
        body: JSON.stringify({
          user_answer: userAnswer,
          question_title: question.title,
          requirements: question.requirements,
          // 如果有图片，也可以放在这里传
          has_images: images && images.length > 0
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