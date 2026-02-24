# 申论智批 - 埋点事件文档

本文档定义网站统计埋点的事件名、说明、触发时机与参数规范，便于产品/运营配置统计平台及后续分析。

---

## 一、页面与访问

| 事件名 | 说明 | 触发时机 | 参数 |
|--------|------|----------|------|
| `page_view` | 页面浏览 | 每次进入某页面时 | `page`: `home` \| `exam` \| `report` \| `profile` |

用于 PV/UV 与访问人数统计。在应用内 `currentPage` 切换时上报。

**示例**：进入做题页 → `page_view`，`page=exam`。

---

## 二、试卷相关

| 事件名 | 说明 | 触发时机 | 参数 |
|--------|------|----------|------|
| `paper_click` | 点击试卷卡片 | 首页点击某张试卷卡片 | `paper_id`, `paper_name`, `exam_type`, `region`, `year` |
| `paper_submit_click` | 点击「提交并批改」 | 做题页点击提交按钮 | `paper_id`, `paper_name`, `question_id`, `question_title` |
| `grading_result` | 批改结果 | 批改请求结束后（成功或失败） | `paper_id`, `paper_name`, `question_id`, `status`: `success` \| `fail`, `error?`（失败时简要原因） |

- 参数来源：`Paper`、`Question` 见 `frontend/types.ts`；`paper_id` 即试卷唯一标识（如 `gwy_anhui_2025_A`）。
- `grading_result` 仅在接口返回后上报一次，成功与失败二选一。

**示例**：
- 首页点击「2025 安徽公务员 A 卷」→ `paper_click`，带该试卷 id/name/type/region/year。
- 做题页点击「提交并批改」→ `paper_submit_click`；批改接口成功 → `grading_result`，`status=success`；接口异常 → `grading_result`，`status=fail`，`error` 为简要错误信息。

---

## 三、按钮与交互

| 事件名 | 说明 | 触发位置 | 参数 |
|--------|------|----------|------|
| `filter_change` | 筛选变更 | 首页考试类型/地区 | `filter_type`: `type` \| `region`, `value` |
| `exam_back` | 做题页返回 | ExamDetail 返回按钮 | `paper_id` |
| `exam_tab_switch` | 材料/题目切换 | 做题页材料 Tab、题目 Tab、移动端「材料/问题」切换 | `tab`: `material` \| `question` |
| `photo_upload_click` | 点击拍照/上传 | 做题页上传答案图片按钮 | `paper_id`, `question_id` |
| `payment_modal_confirm` | 支付弹窗确认批改 | PaymentModal 点「去批改/立即支付/确定」 | 可选 `paper_id` |
| `payment_modal_close` | 支付弹窗关闭 | 关闭弹窗（按钮或遮罩） | 可选 `paper_id` |
| `report_back` | 报告页返回列表 | Report「返回列表」 | 无 |
| `report_copy` | 报告页一键复制 | Report「一键复制」 | 无 |
| `nav_click` | 导航点击 | Navbar 各入口 | `target`: `home` \| `list` \| `history` \| `profile` \| `logout` |
| `history_record_click` | 历史记录点击 | Profile 点击某条记录 | `paper_name`, `record_id` |

- `nav_click` 的 `target`：`home` 为 Logo/首页，`list` 为题库列表，`history` 为历史批改，`profile` 为个人中心，`logout` 为清除缓存。
- 所有带 `paper_id` 的按钮事件，在无试卷上下文时可省略该参数。

---

## 四、统计平台映射说明

- **百度统计**：使用 `_trackEvent(category, action, label, value)`。建议将「事件名」作为 `category`，「动作」作为 `action`，参数拼接为 `label` 或通过多条 event 传递。
- **51.LA**：在后台配置自定义事件名与属性，与上表事件名、参数一一对应即可。

开发环境可通过开关仅打印 log 不上报，避免污染生产数据。
