"""
春招网申自动填表 Agent - 核心表单填充模块
使用 Playwright 自动化浏览器 + LLM 智能字段映射
"""
import json
import asyncio
import re
from pathlib import Path
from playwright.async_api import async_playwright, Page, BrowserContext


async def extract_form_fields(page: Page) -> list[dict]:
    """
    从页面中提取所有表单元素信息
    返回: [{tag, type, name, id, placeholder, label, options, selector, value}]
    """
    fields = await page.evaluate("""
    () => {
        const results = [];
        
        // 提取所有 input, select, textarea
        const inputs = document.querySelectorAll('input, select, textarea');
        inputs.forEach((el, idx) => {
            const field = {
                tag: el.tagName.toLowerCase(),
                type: el.type || '',
                name: el.name || '',
                id: el.id || '',
                placeholder: el.placeholder || '',
                value: el.value || '',
                className: el.className || '',
                selector: '',
                options: [],
                label: '',
                required: el.required || false,
                disabled: el.disabled || false,
                visible: el.offsetParent !== null
            };
            
            // 生成唯一 selector
            if (el.id) {
                field.selector = '#' + el.id;
            } else if (el.name) {
                field.selector = `${el.tagName.toLowerCase()}[name="${el.name}"]`;
            } else {
                field.selector = `${el.tagName.toLowerCase()}:nth-of-type(${idx + 1})`;
            }
            
            // 提取 label（通过 for 属性或父级 label）
            if (el.id) {
                const labelEl = document.querySelector(`label[for="${el.id}"]`);
                if (labelEl) field.label = labelEl.textContent.trim();
            }
            if (!field.label) {
                const parent = el.closest('label, .form-item, .ant-form-item, .el-form-item, [class*="form"], [class*="field"]');
                if (parent) {
                    const labelEl = parent.querySelector('label, .label, [class*="label"], [class*="title"]');
                    if (labelEl) field.label = labelEl.textContent.trim();
                }
            }
            // 兜底：取最近的文本节点
            if (!field.label) {
                const prev = el.previousElementSibling;
                if (prev && prev.textContent.length < 50) {
                    field.label = prev.textContent.trim();
                }
            }
            
            // 提取 select 选项
            if (el.tagName.toLowerCase() === 'select') {
                field.options = Array.from(el.options).map(o => ({
                    value: o.value,
                    text: o.textContent.trim()
                }));
            }
            
            if (field.visible && !field.disabled) {
                results.push(field);
            }
        });
        
        // 也提取 contenteditable 的 div（某些富文本编辑器）
        const editables = document.querySelectorAll('[contenteditable="true"]');
        editables.forEach((el, idx) => {
            results.push({
                tag: 'div',
                type: 'contenteditable',
                name: '',
                id: el.id || '',
                placeholder: el.getAttribute('data-placeholder') || '',
                value: el.textContent || '',
                className: el.className || '',
                selector: el.id ? '#' + el.id : `[contenteditable]:nth-of-type(${idx + 1})`,
                options: [],
                label: '',
                required: false,
                disabled: false,
                visible: true
            });
        });
        
        // 提取所有 Ant Design / 自定义 下拉框触发器
        const antSelects = document.querySelectorAll('.ant-select, [class*="select"], [role="combobox"]');
        antSelects.forEach((el, idx) => {
            const label_el = el.closest('[class*="form-item"], [class*="field"]');
            let label = '';
            if (label_el) {
                const l = label_el.querySelector('[class*="label"], label');
                if (l) label = l.textContent.trim();
            }
            const currentValue = el.querySelector('[class*="selection-item"], [class*="select__value"]');
            results.push({
                tag: 'ant-select',
                type: 'dropdown',
                name: '',
                id: el.id || '',
                placeholder: el.querySelector('[class*="placeholder"]')?.textContent || '',
                value: currentValue?.textContent?.trim() || '',
                className: el.className || '',
                selector: el.id ? '#' + el.id : `.ant-select:nth-of-type(${idx + 1})`,
                options: [],
                label: label,
                required: false,
                disabled: false,
                visible: el.offsetParent !== null
            });
        });
        
        return results;
    }
    """)
    return fields


def build_llm_prompt(form_fields: list[dict], user_profile: dict) -> str:
    """
    构建发给 LLM 的字段映射 Prompt
    """
    # 简化表单字段展示
    fields_summary = []
    for i, f in enumerate(form_fields):
        desc = f"[{i}] "
        if f['label']:
            desc += f"标签: {f['label']} | "
        desc += f"类型: {f['tag']}/{f['type']} | "
        if f['placeholder']:
            desc += f"提示: {f['placeholder']} | "
        if f['name']:
            desc += f"name: {f['name']} | "
        if f['id']:
            desc += f"id: {f['id']} | "
        if f['options']:
            opts = [o['text'] for o in f['options'][:10]]
            desc += f"选项: {opts}"
        if f['value']:
            desc += f" | 当前值: {f['value']}"
        fields_summary.append(desc)

    return f"""你是一个智能表单填写助手。用户需要填写一份招聘申请表。

## 页面表单字段：
{chr(10).join(fields_summary)}

## 用户个人信息（JSON）：
{json.dumps(user_profile, ensure_ascii=False, indent=2)}

## 任务：
请为每个表单字段匹配用户信息，返回一个 JSON 数组。每个元素格式：
{{
  "field_index": 0,
  "action": "fill" | "select" | "click" | "skip",
  "value": "要填入的值",
  "reason": "简短说明为什么这样填"
}}

规则：
1. 如果字段有label或placeholder提示，根据语义匹配最合适的用户信息
2. 如果是下拉框(select/dropdown)，value应该是选项中最匹配的文本
3. 如果无法匹配（比如验证码字段），action设为"skip"
4. 日期字段按照字段要求的格式填写
5. 身份证号等敏感信息也正常填写
6. 只返回JSON数组，不要其他文字
"""


async def fill_form(page: Page, mappings: list[dict], form_fields: list[dict]):
    """
    根据 LLM 返回的映射方案，自动填充表单
    """
    for m in mappings:
        if m['action'] == 'skip':
            continue

        idx = m['field_index']
        if idx >= len(form_fields):
            continue

        field = form_fields[idx]
        selector = field['selector']
        value = m['value']

        try:
            if m['action'] == 'fill':
                # 先清空再填入
                await page.click(selector)
                await page.fill(selector, '')
                await page.fill(selector, str(value))
                await asyncio.sleep(0.3)

            elif m['action'] == 'select':
                if field['tag'] == 'select':
                    await page.select_option(selector, label=str(value))
                elif field['tag'] == 'ant-select':
                    # Ant Design 下拉框处理
                    await page.click(selector)
                    await asyncio.sleep(0.5)
                    # 如果有搜索框，输入搜索
                    search = page.locator('.ant-select-dropdown input, .ant-select-search__field')
                    if await search.count() > 0:
                        await search.fill(str(value))
                        await asyncio.sleep(0.5)
                    # 点击匹配的选项
                    option = page.locator(f'.ant-select-dropdown-menu-item, .ant-select-item-option').filter(has_text=str(value)).first
                    if await option.count() > 0:
                        await option.click()
                    await asyncio.sleep(0.3)

            elif m['action'] == 'click':
                await page.click(selector)
                await asyncio.sleep(0.3)

            print(f"  ✅ [{idx}] {field.get('label', field.get('name', '未知'))} ← {value}")

        except Exception as e:
            print(f"  ⚠️ [{idx}] {field.get('label', field.get('name', '未知'))} 填写失败: {e}")


async def screenshot_and_confirm(page: Page, step_name: str, save_dir: str = "./screenshots"):
    """
    截图并等待用户确认
    """
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


def call_llm_for_mapping(prompt: str, api_key: str = None, model: str = "gpt-4o") -> list[dict]:
    """
    调用 LLM 进行字段映射
    支持 OpenAI API
    """
    try:
        from openai import OpenAI
        client = OpenAI(api_key=api_key)
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": "你是一个精确的表单字段匹配助手。只返回JSON数组，不要任何其他文字。"},
                {"role": "user", "content": prompt}
            ],
            temperature=0,
            response_format={"type": "json_object"}
        )
        content = response.choices[0].message.content
        # 解析 JSON
        data = json.loads(content)
        if isinstance(data, dict) and 'mappings' in data:
            return data['mappings']
        elif isinstance(data, list):
            return data
        else:
            # 尝试提取数组
            return list(data.values())[0] if data else []
    except ImportError:
        print("❌ 需要安装 openai 包: pip install openai")
        raise
    except Exception as e:
        print(f"❌ LLM 调用失败: {e}")
        raise
