# 🤖 AutoApply Agent

[![Python](https://img.shields.io/badge/Python-3.8+-blue.svg)](https://python.org)
[![Playwright](https://img.shields.io/badge/Playwright-Automation-green.svg)](https://playwright.dev)
[![OpenAI](https://img.shields.io/badge/OpenAI-GPT--4o-purple.svg)](https://openai.com)
[![Streamlit](https://img.shields.io/badge/Streamlit-Web_UI-red.svg)](https://streamlit.io)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

> 🎓 AI 驱动的春招网申自动填表工具 — 输入个人信息 + 粘贴链接 = 一键填写申请表

## ✨ 核心特性

| 特性 | 说明 |
|------|------|
| 🧠 **LLM 智能映射** | 用 AI 理解表单字段语义，不依赖硬编码，适配任意公司官网 |
| 🛡️ **数据纯本地** | 所有个人信息保存在本地，不上传任何服务器 |
| ✋ **人工确认提交** | AI 负责填写，你负责审核和提交，安全可控 |
| 📄 **多页表单支持** | 自动检测「下一步」按钮，逐页填写 |
| 🖥️ **双模式使用** | CLI 命令行 + Streamlit Web UI |

## 🚀 快速开始

### 安装

```bash
git clone https://github.com/hanjiayuan2025-coder/auto-apply-agent.git
cd auto-apply-agent
pip install -r requirements.txt
playwright install chromium
```

### 方式一：命令行模式（推荐）

```bash
# 1. 编辑 user_profile.json 填入你的个人信息
# 2. 设置 API Key
export OPENAI_API_KEY="sk-xxx"

# 3. 运行！
python run.py --url "https://campus.163.com/app/detail/index?id=3494&projectId=69"
```

### 方式二：Web UI 模式

```bash
streamlit run app.py
# 浏览器自动打开 http://localhost:8501
```

## 🏗️ 工作原理

```
┌─────────────────────────────────────────────────────────┐
│                    AutoApply Agent                       │
├─────────────────────────────────────────────────────────┤
│                                                         │
│  📝 user_profile.json    🔗 目标网申 URL                 │
│         │                       │                       │
│         ▼                       ▼                       │
│  ┌─────────────────────────────────────────┐            │
│  │     Playwright 浏览器自动化               │            │
│  │  打开页面 → 提取所有 input/select/textarea │            │
│  └────────────────┬────────────────────────┘            │
│                   │                                     │
│                   ▼                                     │
│  ┌─────────────────────────────────────────┐            │
│  │     LLM 智能字段映射 (GPT-4o-mini)       │            │
│  │  表单标签/placeholder ↔ 用户 JSON 字段    │            │
│  └────────────────┬────────────────────────┘            │
│                   │                                     │
│                   ▼                                     │
│  ┌─────────────────────────────────────────┐            │
│  │     自动填充 + 截图确认                    │            │
│  │  每页填完截图 → 用户确认 → 下一页          │            │
│  └─────────────────────────────────────────┘            │
│                                                         │
│  ⚠️ 不会自动提交 — 最终由你手动点击提交按钮     │
└─────────────────────────────────────────────────────────┘
```

## 📁 项目结构

```
auto-apply-agent/
├── run.py              # CLI 入口（个人使用）
├── app.py              # Streamlit Web UI（通用产品）
├── form_filler.py      # 核心：表单提取 + LLM 映射 + 自动填充
├── user_profile.json   # 你的个人信息模板
├── requirements.txt    # Python 依赖
├── screenshots/        # 自动生成的填写截图
├── LICENSE             # MIT 开源协议
└── README.md           # 本文件
```

## 🎯 支持的平台

理论上支持**所有公司**的校招网站，因为使用 LLM 做智能语义映射。已测试的平台包括：

- 网易校招 (campus.163.com)
- 更多平台持续验证中...

## ⚙️ 进阶用法

```bash
# 使用本地 Chrome（复用已登录状态，推荐！）
python run.py --url "https://xxx.com/apply" \
  --user-data-dir ~/Library/Application\ Support/Google/Chrome/Default

# 使用更强的模型
python run.py --url "https://xxx.com/apply" --model gpt-4o

# 无头模式（不显示浏览器窗口）
python run.py --url "https://xxx.com/apply" --headless
```

## 🔐 隐私与安全

- ✅ 所有个人信息**仅保存在你的本地电脑**
- ✅ 发给 LLM 的只是**表单结构**（字段名/标签），不包含你的完整个人信息
- ✅ 不会自动提交表单
- ✅ 开源代码，可审计

## 💰 费用

脚本本身**完全免费**。使用 GPT-4o-mini 做字段映射，每次填表消耗约 **$0.01**（不到 1 毛钱）。

## 🤝 贡献

欢迎 PR！特别欢迎以下方向的贡献：

- 支持更多招聘平台的适配测试
- 支持更多下拉框组件的识别（Element UI、Ant Design 等）
- 支持简历 PDF 自动解析导入

## 📄 License

[MIT](LICENSE)

---

> 🎓 祝大家春招顺利，拿到心仪的 Offer！
