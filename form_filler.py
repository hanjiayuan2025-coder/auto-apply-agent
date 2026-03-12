"""
春招网申自动填表 Agent - 核心表单填充模块 v2
使用 Playwright 自动化浏览器 + LLM 智能字段映射

v2 改进：
- 使用 LLM 直接分析页面 HTML 结构来识别表单，而非硬编码选择器
- 支持 React/Ant Design/自定义组件
- 更强大的交互式填充逻辑
"""
import json
import asyncio
import re
from pathlib import Path
from playwright.async_api import async_playwright, Page, BrowserContext


async def get_page_structure(page: Page) -> str:
    """
    获取页面可交互元素的简化结构（发给LLM分析）
    遍历所有可见DOM节点，提取可交互元素和标签文本
    """
    structure = await page.evaluate("""
    () => {
        function getPath(el) {
            const parts = [];
            let node = el;
            while (node && node !== document.body) {
                let selector = node.tagName.toLowerCase();
                if (node.id) {
                    selector += '#' + node.id;
                } else if (node.className && typeof node.className === 'string') {
                    const cls = node.className.trim().split(/\\s+/).slice(0, 2).join('.');
                    if (cls) selector += '.' + cls;
                }
                parts.unshift(selector);
                node = node.parentElement;
            }
            return parts.join(' > ');
        }
        
        const results = [];
        
        // 策略1: 所有可交互元素
        const interactives = document.querySelectorAll(
            'input, select, textarea, ' +
            '[role="textbox"], [role="combobox"], [role="listbox"], [role="spinbutton"], ' +
            '[contenteditable="true"], ' +
            '[class*="input"], [class*="select"], [class*="picker"], [class*="upload"], ' +
            '[class*="radio"], [class*="checkbox"], [class*="switch"], [class*="cascader"]'
        );
        
        interactives.forEach((el, idx) => {
            if (el.offsetParent === null && el.type !== 'hidden') return; // 不可见
            
            // 找最近的标签文本
            let label = '';
            // 方法1: 关联 label
            if (el.id) {
                const lbl = document.querySelector('label[for="' + el.id + '"]');
                if (lbl) label = lbl.textContent.trim();
            }
            // 方法2: 父级容器中找标签
            if (!label) {
                let parent = el.parentElement;
                for (let i = 0; i < 8 && parent; i++) {
                    const lbl = parent.querySelector('label, [class*="label"], [class*="title"], [class*="name"]');
                    if (lbl && lbl.textContent.trim().length < 30 && !lbl.contains(el)) {
                        label = lbl.textContent.trim();
                        break;
                    }
                    // 也找前面的兄弟元素
                    const prevSib = parent.previousElementSibling;
                    if (prevSib && prevSib.textContent.trim().length < 30) {
                        label = prevSib.textContent.trim();
                        break;
                    }
                    parent = parent.parentElement;
                }
            }
            // 方法3: aria-label
            if (!label) label = el.getAttribute('aria-label') || '';
            
            results.push({
                index: idx,
                tag: el.tagName.toLowerCase(),
                type: el.type || el.getAttribute('role') || '',
                id: el.id || '',
                name: el.name || '',
                className: (el.className && typeof el.className === 'string') ? el.className.split(' ').slice(0, 3).join(' ') : '',
                placeholder: el.placeholder || el.getAttribute('data-placeholder') || '',
                value: el.value || el.textContent?.substring(0, 50) || '',
                label: label,
                path: getPath(el),
                required: el.required || el.getAttribute('aria-required') === 'true',
                disabled: el.disabled || el.getAttribute('aria-disabled') === 'true',
                visible: el.offsetParent !== null || el.type === 'hidden'
            });
        });
        
        // 策略2: 扫描页面上所有可见的表单区域（带标签文本的块）
        const formBlocks = document.querySelectorAll(
            '[class*="form-item"], [class*="form_item"], [class*="formItem"], ' +
            '[class*="field"], [class*="cell"], [class*="item"]'
        );
        
        formBlocks.forEach((block) => {
            if (block.offsetParent === null) return;
            
            // 找标签
            const labelEl = block.querySelector('[class*="label"], label, [class*="title"], [class*="name"]');
            const label = labelEl ? labelEl.textContent.trim() : '';
            if (!label || label.length > 30) return;
            
            // 找可交互子元素
            const input = block.querySelector('input, select, textarea, [role="textbox"], [role="combobox"], [contenteditable]');
            if (input) return; // 已被策略1覆盖
            
            // 找可点击区域(自定义下拉框等)
            const clickable = block.querySelector('[class*="value"], [class*="content"], [class*="placeholder"], [class*="trigger"]');
            if (clickable) {
                results.push({
                    index: results.length,
                    tag: 'custom',
                    type: 'clickable',
                    id: clickable.id || '',
                    name: '',
                    className: (clickable.className && typeof clickable.className === 'string') ? clickable.className.split(' ').slice(0, 3).join(' ') : '',
                    placeholder: clickable.textContent?.substring(0, 50)?.trim() || '',
                    value: '',
                    label: label,
                    path: getPath(clickable),
                    required: false,
                    disabled: false,
                    visible: true
                });
            }
        });
        
        return JSON.stringify(results, null, 2);
    }
    """)
    return structure


async def get_page_text_snapshot(page: Page) -> str:
    """
    获取页面的文本快照（用于LLM理解当前上下文）
    """
    text = await page.evaluate("""
    () => {
        const walker = document.createTreeWalker(
            document.body, 
            NodeFilter.SHOW_TEXT,
            { acceptNode: (node) => {
                if (!node.parentElement) return NodeFilter.FILTER_REJECT;
                if (node.parentElement.offsetParent === null) return NodeFilter.FILTER_REJECT;
                if (['SCRIPT','STYLE','NOSCRIPT'].includes(node.parentElement.tagName)) return NodeFilter.FILTER_REJECT;
                if (node.textContent.trim().length === 0) return NodeFilter.FILTER_REJECT;
                return NodeFilter.FILTER_ACCEPT;
            }}
        );
        const texts = [];
        while (walker.nextNode()) {
            const t = walker.currentNode.textContent.trim();
            if (t && !texts.includes(t)) texts.push(t);
        }
        return texts.join('\\n').substring(0, 3000);
    }
    """)
    return text


def build_analysis_prompt(page_elements: str, page_text: str, user_profile: dict) -> str:
    """
    构建让 LLM 分析页面并生成填写方案的 Prompt
    """
    return f"""你是一个网申自动填表 AI。分析以下页面结构，判断哪些元素需要填写，并生成填充方案。

## 页面可交互元素（JSON数组）：
{page_elements}

## 页面可见文字：
{page_text}

## 用户个人信息：
{json.dumps(user_profile, ensure_ascii=False, indent=2)}

## 任务：
1. 分析每个可交互元素的 label/placeholder/id/name，理解它代表什么字段
2. 匹配用户信息中对应的值
3. 返回 JSON 对象，格式：

{{
  "page_description": "简述当前页面是什么（如：个人信息填写页/教育经历页/投递确认页）",
  "actions": [
    {{
      "index": 0,
      "action": "fill",
      "selector": "用 CSS selector 或 XPath 定位元素",
      "value": "要填入的值",
      "method": "type | click | select | upload | skip",
      "reason": "为什么这样填"
    }}
  ]
}}

method 说明：
- "type": 在输入框中输入文字（先清空再输入）
- "click": 点击该元素（用于按钮/单选/复选）
- "select": 下拉框选择（先点击展开，再搜索/点选）
- "upload": 需要上传文件（跳过，让用户手动）
- "skip": 跳过不填

重要规则：
- 使用元素的 path 字段来构造可靠的 selector
- 如果元素已有正确的值(value)，跳过不填
- 如果是隐藏字段(hidden)，跳过
- 如果是日期字段，格式用 YYYY-MM-DD
- 只返回JSON，不要其他文字"""


async def execute_actions(page: Page, actions: list[dict]):
    """
    执行 LLM 生成的填写动作
    """
    for act in actions:
        if act.get('method') in ('skip', 'upload'):
            reason = act.get('reason', '')
            print(f"  ⏭️  跳过: {reason}")
            continue

        selector = act.get('selector', '')
        value = act.get('value', '')
        method = act.get('method', 'type')

        if not selector:
            continue

        try:
            # 尝试定位元素
            element = page.locator(selector).first
            if await element.count() == 0:
                # 尝试用 text 定位
                if act.get('reason'):
                    print(f"  ⚠️  找不到元素: {selector}")
                continue

            if method == 'type':
                await element.click()
                await asyncio.sleep(0.2)
                await element.fill('')
                await element.fill(str(value))
                await asyncio.sleep(0.3)
                # 触发 React onChange
                await element.dispatch_event('input')
                await element.dispatch_event('change')
                print(f"  ✅ 输入: {act.get('reason', selector)} ← {value}")

            elif method == 'click':
                await element.click()
                await asyncio.sleep(0.5)
                print(f"  ✅ 点击: {act.get('reason', selector)}")

            elif method == 'select':
                # 先点击展开下拉框
                await element.click()
                await asyncio.sleep(0.8)

                # 尝试在下拉面板中找到匹配项
                # 通用策略：找所有可见的列表项
                option_selectors = [
                    f'[class*="dropdown"] [class*="item"]:has-text("{value}")',
                    f'[class*="option"]:has-text("{value}")',
                    f'[role="option"]:has-text("{value}")',
                    f'.ant-select-item-option:has-text("{value}")',
                    f'li:has-text("{value}")',
                ]
                
                clicked = False
                for opt_sel in option_selectors:
                    opt = page.locator(opt_sel).first
                    if await opt.count() > 0:
                        await opt.click()
                        clicked = True
                        break

                if not clicked:
                    # 如果有搜索框，输入搜索
                    search_selectors = [
                        '[class*="dropdown"] input',
                        '[class*="search"] input',
                        '.ant-select-search__field',
                    ]
                    for s_sel in search_selectors:
                        search_input = page.locator(s_sel).first
                        if await search_input.count() > 0:
                            await search_input.fill(str(value))
                            await asyncio.sleep(0.5)
                            # 点第一个搜索结果
                            first_result = page.locator('[class*="option"], [class*="item"], li').first
                            if await first_result.count() > 0:
                                await first_result.click()
                                clicked = True
                            break

                if clicked:
                    print(f"  ✅ 选择: {act.get('reason', selector)} ← {value}")
                else:
                    print(f"  ⚠️  下拉选择失败: {act.get('reason', '')} | 值: {value}")

                await asyncio.sleep(0.3)

        except Exception as e:
            print(f"  ⚠️  操作失败 [{method}]: {act.get('reason', selector)} | 错误: {e}")


async def screenshot_and_confirm(page: Page, step_name: str, save_dir: str = "./screenshots"):
    """截图并等待用户确认"""
    Path(save_dir).mkdir(exist_ok=True)
    path = f"{save_dir}/{step_name}.png"
    await page.screenshot(path=path, full_page=True)
    print(f"\n📸 已截图保存到: {path}")
    print("请检查填写是否正确。")
    response = input("输入 'y' 确认继续，输入 'n' 取消，输入 'r' 重新填写: ").strip().lower()
    return response


def load_user_profile(profile_path: str) -> dict:
    """加载用户信息 JSON"""
    with open(profile_path, 'r', encoding='utf-8') as f:
        return json.load(f)


def call_llm_for_analysis(prompt: str, api_key: str = None, model: str = "gpt-4o") -> dict:
    """
    调用 LLM 分析页面并返回填写方案
    """
    try:
        from openai import OpenAI
        client = OpenAI(api_key=api_key)
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": "你是一个精确的网申表单填写助手。分析页面元素结构，返回JSON格式的填写方案。只返回JSON。"},
                {"role": "user", "content": prompt}
            ],
            temperature=0,
            response_format={"type": "json_object"}
        )
        content = response.choices[0].message.content
        return json.loads(content)
    except ImportError:
        print("❌ 需要安装 openai 包: pip install openai")
        raise
    except Exception as e:
        print(f"❌ LLM 调用失败: {e}")
        raise
