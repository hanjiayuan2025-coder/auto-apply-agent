"""
AutoApply Agent - 春招网申自动填表 AI Agent
Streamlit Web UI - 让所有人都能用的版本
"""
import streamlit as st
import json
import asyncio
import os
import sys
from pathlib import Path
from datetime import datetime

# 页面配置
st.set_page_config(
    page_title="AutoApply Agent - AI 自动填网申",
    page_icon="🤖",
    layout="wide",
    initial_sidebar_state="expanded"
)

# 自定义样式
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap');

* { font-family: 'Inter', sans-serif; }

.main-header {
    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
    padding: 2rem;
    border-radius: 16px;
    color: white;
    margin-bottom: 2rem;
    text-align: center;
}
.main-header h1 { 
    font-size: 2.2rem; 
    font-weight: 700; 
    margin: 0;
    text-shadow: 0 2px 4px rgba(0,0,0,0.1);
}
.main-header p { 
    font-size: 1rem; 
    opacity: 0.9; 
    margin: 0.5rem 0 0 0; 
}

.step-card {
    background: white;
    border: 1px solid #e2e8f0;
    border-radius: 12px;
    padding: 1.5rem;
    margin: 1rem 0;
    box-shadow: 0 1px 3px rgba(0,0,0,0.04);
}
.step-card h3 {
    color: #334155;
    margin: 0 0 0.5rem 0;
}

.status-badge {
    display: inline-block;
    padding: 4px 12px;
    border-radius: 20px;
    font-size: 0.8rem;
    font-weight: 500;
}
.status-ready { background: #dcfce7; color: #166534; }
.status-running { background: #fef3c7; color: #92400e; }
.status-done { background: #dbeafe; color: #1e40af; }

.feature-grid {
    display: grid;
    grid-template-columns: repeat(3, 1fr);
    gap: 1rem;
    margin: 1.5rem 0;
}
.feature-item {
    background: #f8fafc;
    border-radius: 12px;
    padding: 1.2rem;
    text-align: center;
}
.feature-item .icon { font-size: 2rem; margin-bottom: 0.5rem; }
.feature-item h4 { color: #334155; margin: 0.3rem 0; font-size: 0.95rem; }
.feature-item p { color: #64748b; font-size: 0.8rem; margin: 0; }
</style>
""", unsafe_allow_html=True)


def init_session_state():
    """初始化 session state"""
    defaults = {
        'profile_data': None,
        'target_url': '',
        'api_key': '',
        'fill_status': 'idle',  # idle, running, done, error
        'fill_log': [],
        'current_page': 'home'
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v


def render_home():
    """首页"""
    st.markdown("""
    <div class="main-header">
        <h1>🤖 AutoApply Agent</h1>
        <p>AI 驱动的春招网申自动填表工具 · 输入信息 → 粘贴链接 → 一键填写</p>
    </div>
    """, unsafe_allow_html=True)

    st.markdown("""
    <div class="feature-grid">
        <div class="feature-item">
            <div class="icon">🧠</div>
            <h4>LLM 智能映射</h4>
            <p>AI 理解表单语义，不依赖硬编码</p>
        </div>
        <div class="feature-item">
            <div class="icon">🛡️</div>
            <h4>数据纯本地</h4>
            <p>个人信息不上传任何第三方</p>
        </div>
        <div class="feature-item">
            <div class="icon">✋</div>
            <h4>人工确认提交</h4>
            <p>AI 填写，你来检查和提交</p>
        </div>
    </div>
    """, unsafe_allow_html=True)

    st.markdown("### 🚀 快速开始")
    col1, col2, col3 = st.columns(3)
    with col1:
        if st.button("📝 第一步：录入个人信息", use_container_width=True, type="primary"):
            st.session_state.current_page = 'profile'
            st.rerun()
    with col2:
        btn_disabled = st.session_state.profile_data is None
        if st.button("🎯 第二步：开始填表", use_container_width=True, disabled=btn_disabled):
            st.session_state.current_page = 'fill'
            st.rerun()
    with col3:
        if st.button("📖 使用说明", use_container_width=True):
            st.session_state.current_page = 'help'
            st.rerun()

    if st.session_state.profile_data:
        st.success(f"✅ 已加载个人信息：{st.session_state.profile_data.get('basic_info', {}).get('name', '未知')}")


def render_profile_editor():
    """个人信息录入页"""
    st.markdown("## 📝 个人信息录入")
    st.caption("填写你的基本信息，用于自动填写网申表单。所有数据仅保存在本地。")

    tab1, tab2 = st.tabs(["📋 表单填写", "📄 JSON 导入"])

    with tab1:
        with st.form("profile_form"):
            st.markdown("### 基本信息")
            col1, col2, col3 = st.columns(3)
            with col1:
                name = st.text_input("姓名 *", value="")
                gender = st.selectbox("性别", ["男", "女"])
                phone = st.text_input("手机号 *")
            with col2:
                email = st.text_input("邮箱 *")
                birthday = st.date_input("出生日期")
                ethnicity = st.text_input("民族", value="汉族")
            with col3:
                id_number = st.text_input("身份证号")
                political_status = st.selectbox("政治面貌", ["共青团员", "中共党员", "群众", "民主党派"])
                address = st.text_input("家庭住址")

            st.markdown("### 最高学历")
            col1, col2 = st.columns(2)
            with col1:
                edu_level = st.selectbox("学历", ["硕士", "本科", "博士"])
                school = st.text_input("学校名称 *")
                major = st.text_input("专业 *")
            with col2:
                edu_start = st.date_input("入学时间", key="edu_start")
                edu_end = st.date_input("毕业时间", key="edu_end")
                is_overseas = st.checkbox("是否海外学历")

            st.markdown("### 最近实习经历")
            col1, col2 = st.columns(2)
            with col1:
                company = st.text_input("公司名称")
                position = st.text_input("岗位名称")
            with col2:
                work_start = st.date_input("开始时间", key="work_start")
                work_end = st.date_input("结束时间", key="work_end")
            work_desc = st.text_area("工作描述", height=100)

            submitted = st.form_submit_button("💾 保存个人信息", type="primary", use_container_width=True)

            if submitted and name and phone and email:
                profile = {
                    "basic_info": {
                        "name": name, "gender": gender, "phone": phone,
                        "email": email, "birthday": str(birthday),
                        "ethnicity": ethnicity, "id_number": id_number,
                        "political_status": political_status, "address": address
                    },
                    "education": [{
                        "level": edu_level, "school": school, "major": major,
                        "start_date": str(edu_start), "end_date": str(edu_end),
                        "is_overseas": is_overseas
                    }],
                    "work_experience": [{
                        "company": company, "position": position,
                        "start_date": str(work_start), "end_date": str(work_end),
                        "description": work_desc
                    }] if company else []
                }
                st.session_state.profile_data = profile
                # 保存到文件
                save_path = Path(__file__).parent / "user_profile.json"
                with open(save_path, 'w', encoding='utf-8') as f:
                    json.dump(profile, f, ensure_ascii=False, indent=2)
                st.success("✅ 个人信息已保存！")

    with tab2:
        st.markdown("如果你已经有 `user_profile.json` 文件，可以直接上传或粘贴：")
        
        uploaded = st.file_uploader("上传 JSON 文件", type=["json"])
        if uploaded:
            try:
                data = json.loads(uploaded.read().decode('utf-8'))
                st.session_state.profile_data = data
                st.success(f"✅ 已导入：{data.get('basic_info', {}).get('name', '未知')}")
                st.json(data)
            except Exception as e:
                st.error(f"JSON 解析失败: {e}")

        json_text = st.text_area("或者直接粘贴 JSON", height=200)
        if st.button("📥 导入 JSON") and json_text:
            try:
                data = json.loads(json_text)
                st.session_state.profile_data = data
                st.success(f"✅ 已导入：{data.get('basic_info', {}).get('name', '未知')}")
            except Exception as e:
                st.error(f"JSON 解析失败: {e}")

    if st.button("← 返回首页"):
        st.session_state.current_page = 'home'
        st.rerun()


def render_fill_page():
    """填表页"""
    st.markdown("## 🎯 开始自动填表")

    if not st.session_state.profile_data:
        st.warning("⚠️ 请先录入个人信息")
        if st.button("去录入"):
            st.session_state.current_page = 'profile'
            st.rerun()
        return

    profile = st.session_state.profile_data
    st.success(f"✅ 当前用户：{profile.get('basic_info', {}).get('name', '未知')}")

    col1, col2 = st.columns([3, 1])
    with col1:
        url = st.text_input(
            "🔗 目标网申 URL",
            placeholder="粘贴公司校招申请页面的链接，如 https://campus.163.com/...",
            value=st.session_state.target_url
        )
    with col2:
        api_key = st.text_input(
            "🔑 OpenAI API Key",
            type="password",
            value=st.session_state.api_key or os.environ.get('OPENAI_API_KEY', '')
        )

    model = st.selectbox("模型选择", ["gpt-4o-mini", "gpt-4o", "gpt-3.5-turbo"], index=0)

    if st.button("🚀 开始自动填写", type="primary", use_container_width=True, disabled=not url or not api_key):
        st.session_state.target_url = url
        st.session_state.api_key = api_key

        st.info("🤖 启动中... 请在弹出的浏览器窗口中操作")
        st.markdown("""
        **接下来会发生什么：**
        1. 🌐 自动打开 Chromium 浏览器
        2. 🔐 如需登录，请在浏览器中手动登录
        3. 📋 AI 自动识别表单字段
        4. ✍️ 自动填写（在终端中确认）
        5. ✅ 你手动检查并提交
        """)

        # 生成运行命令
        profile_path = Path(__file__).parent / "user_profile.json"
        with open(profile_path, 'w', encoding='utf-8') as f:
            json.dump(profile, f, ensure_ascii=False, indent=2)

        cmd = f'cd "{Path(__file__).parent}" && OPENAI_API_KEY="{api_key}" python3 run.py --url "{url}" --model {model}'
        
        st.code(cmd, language="bash")
        st.warning("⚠️ 请复制上面的命令到终端运行（Streamlit 无法直接启动交互式浏览器会话）")

        # 或者直接启动
        if st.button("🖥️ 直接在后台运行"):
            os.system(f'osascript -e \'tell app "Terminal" to do script "{cmd}"\'')
            st.success("✅ 已在新终端窗口启动！请切换到终端查看。")

    if st.button("← 返回首页"):
        st.session_state.current_page = 'home'
        st.rerun()


def render_help():
    """使用说明页"""
    st.markdown("""
    ## 📖 使用说明

    ### 工作原理
    ```
    你的个人信息(JSON) + 目标网申URL
           ↓
    Playwright 打开浏览器，提取页面表单结构
           ↓
    LLM (GPT-4o) 智能匹配：表单字段 ↔ 你的信息
           ↓
    自动填写 → 截图确认 → 你手动提交
    ```

    ### FAQ

    **Q: 支持哪些公司的校招网站？**
    A: 理论上支持所有公司——因为用的是 LLM 智能字段映射，不依赖硬编码。包括网易、字节、阿里、腾讯、美团等。

    **Q: 会自动提交吗？**
    A: **不会**。最终提交必须由你手动点击。

    **Q: 我的个人信息安全吗？**
    A: 完全安全。所有数据保存在你本地电脑，不上传任何第三方服务器。唯一的外部调用是 OpenAI API（发送的是表单结构，不是你的完整个人信息）。

    **Q: 需要什么费用？**
    A: 脚本本身免费。使用 GPT-4o-mini 做字段映射，每次填表大约消耗 $0.01（不到 1 毛钱）。

    **Q: 遇到验证码怎么办？**
    A: 脚本不处理验证码，需要你手动完成。
    """)

    if st.button("← 返回首页"):
        st.session_state.current_page = 'home'
        st.rerun()


# 主逻辑
init_session_state()

# 侧边栏
with st.sidebar:
    st.markdown("### 🤖 AutoApply Agent")
    st.caption("AI 驱动的网申自动填表")
    st.divider()

    pages = {
        'home': '🏠 首页',
        'profile': '📝 个人信息',
        'fill': '🎯 开始填表',
        'help': '📖 使用说明'
    }
    for key, label in pages.items():
        if st.button(label, use_container_width=True,
                     type="primary" if st.session_state.current_page == key else "secondary"):
            st.session_state.current_page = key
            st.rerun()

    st.divider()
    if st.session_state.profile_data:
        name = st.session_state.profile_data.get('basic_info', {}).get('name', '')
        st.markdown(f"👤 **当前用户**: {name}")
    else:
        st.caption("⚠️ 未录入个人信息")

    st.divider()
    st.caption("Made with ❤️ by AutoApply")
    st.caption("[GitHub](https://github.com/hanjiayuan2025-coder/auto-apply-agent)")

# 路由
page_map = {
    'home': render_home,
    'profile': render_profile_editor,
    'fill': render_fill_page,
    'help': render_help
}
page_map.get(st.session_state.current_page, render_home)()
