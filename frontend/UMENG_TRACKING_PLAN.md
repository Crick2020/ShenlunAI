# 爱学申论 U-App 埋点方案

Android 原生层通过 `UmengAnalyticsPlugin` 调用 `MobclickAgent.onEventObject`，前端所有事件仍统一定义在 `services/analytics.ts`。

## 核心转化漏斗

```text
首页浏览
  → 筛选/点击试卷
  → 开始作答
  → 提交批改
  → 批改成功/失败
```

## 事件定义

| 事件 ID | 触发时机 | 参数 |
|---|---|---|
| `um_page_view` | 页面切换 | `page` |
| `um_paper_click` | 点击试卷卡片 | `paper_id`、`exam_type`、`region`、`year` |
| `um_filter_change` | 修改考试类型或地区 | `filter_type`、`filter_value` |
| `um_exam_tab_switch` | 材料/问题切换 | `tab` |
| `um_question_switch` | 切换题目 | `question_type`、`question_index` |
| `um_answer_start` | 首次输入答案 | `question_type` |
| `um_photo_upload` | 拍照、上传或粘贴图片 | `source` |
| `um_grade_submit` | 提交批改 | `question_type`、`answer_length_bucket` |
| `um_grade_result` | 批改接口返回 | `question_type`、`status` |
| `um_history_open` | 打开历史批改 | 无 |
| `um_report_copy` | 复制批改报告 | 无 |
| `um_nav_click` | 点击导航 | `target` |

`answer_length_bucket` 取值为 `0_200`、`201_500`、`501_1000`、`1001_plus`。

## 隐私边界

不上传试卷名称、题目正文、学生作答、批改正文、错误原文、历史记录 ID、设备唯一标识或其他个人信息。所有参数经过前后端双重白名单校验，单个字符串最多 128 个字符、最多 8 个参数。

## 验证

1. 在友盟后台进入「集成测试」，添加测试设备。
2. 启动 App，依次完成首页浏览、打开试卷、开始作答、提交批改。
3. 在实时日志中检查上述事件 ID 和参数。
4. 次日可通过 U-App 自定义事件报表查看事件次数、独立用户和参数分布。
