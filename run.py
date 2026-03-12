#!/usr/bin/env python3
"""
春招网申自动填表 Agent v2 - CLI 入口
用法: python run.py --url "https://campus.163.com/app/..." --profile user_profile.json

v2: 使用 LLM 直接分析页面结构，支持任意 React/SPA 网站
"""
import argparse
import asyncio
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from form_filler import (
    get_page_structure,
    get_page_text_snapshot,
    build_analysis_prompt,
    execute_actions,
    screenshot_and_confirm,
    load_user_profile,
    call_llm_for_analysis
)
from playwright.async_api import async_playwright


async def main():
    parser = argparse.ArgumentParser(description='春招网申自动填表 Agent v2 🤖')
    parser.add_argument('--url', required=True, help='目标网申页面 URL')
    parser.add_argument('--profile', default='user_profile.json', help='用户信息 JSON 文件路径')
    parser.add_argument('--api-key', default=None, help='OpenAI API Key')
    parser.add_argument('--model', default='gpt-4o-mini', help='LLM 模型')
    parser.add_argument('--headless', action='store_true', help='无头模式')
    parser.add_argument('--slow', type=int, default=100, help='操作间隔毫秒')
    parser.add_argument('--chrome-path', default=None, help='Chrome 路径')
    parser.add_argument('--user-data-dir', default=None, help='Chrome 用户数据目录')
    args = parser.parse_args()

    # 加载用户信息
    profile_path = Path(args.profile)
    if not profile_path.is_absolute():
        profile_path = Path(__file__).parent / profile_path
    if not profile_path.exists():
        print(f"❌ 用户信息文件不存在: {profile_path}")
        sys.exit(1)
    
    user_profile = load_user_profile(str(profile_path))
    print(f"✅ 已加载用户信息: {user_profile['basic_info']['name']}")

    # API Key
    api_key = args.api_key or os.environ.get('OPENAI_API_KEY')
    if not api_key:
        api_key = input("请输入你的 OpenAI API Key: ").strip()
        if not api_key:
            print("❌ 需要 API Key")
            sys.exit(1)

    # Chrome 路径
    chrome_path = args.chrome_path
    if not chrome_path:
        for p in ['/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
                   '/usr/bin/google-chrome', '/usr/bin/chromium-browser']:
            if os.path.exists(p):
                chrome_path = p
                break

    print(f"\n🚀 春招网申自动填表 Agent v2 启动")
    print(f"   目标: {args.url}")
    print(f"   模型: {args.model}")
    print("=" * 60)

    async with async_playwright() as p:
        launch_args = {'headless': args.headless, 'slow_mo': args.slow}
        if chrome_path:
            launch_args['executable_path'] = chrome_path

        if args.user_data_dir:
            context = await p.chromium.launch_persistent_context(
                args.user_data_dir, **launch_args,
                viewport={'width': 1280, 'height': 900}
            )
            page = context.pages[0] if context.pages else await context.new_page()
            browser = None
        else:
            browser = await p.chromium.launch(**launch_args)
            context = await browser.new_context(
                viewport={'width': 1280, 'height': 900}, locale='zh-CN'
            )
            page = await context.new_page()

        try:
            # Step 1: 打开页面
            print("\n📄 Step 1: 打开目标页面...")
            await page.goto(args.url, wait_until='networkidle', timeout=30000)
            await asyncio.sleep(3)
            
            title = await page.title()
            print(f"   页面标题: {title}")

            # 检查登录
            body_text = await page.inner_text('body')
            if '登录' in body_text and '注册' in body_text:
                print("\n⚠️  检测到可能需要登录。")
                print("   请在浏览器窗口中手动登录，完成后按 Enter 继续...")
                input("   [按 Enter 继续]")
                await asyncio.sleep(2)
                await page.wait_for_load_state('networkidle')

            # 检查投递按钮
            apply_btn = page.locator('button:has-text("申请"), button:has-text("投递"), a:has-text("申请"), a:has-text("投递"), button:has-text("Apply"), span:has-text("投递")')
            if await apply_btn.count() > 0:
                print("\n🔘 检测到「投递/申请」按钮")
                choice = input("   输入 'y' 点击进入，输入 'n' 跳过: ").strip().lower()
                if choice == 'y':
                    # 使用 force click 绕过可能的遮罩
                    await apply_btn.first.click(force=True)
                    await asyncio.sleep(3)

                    # 检测弹窗（Ant Design Modal）
                    modal = page.locator('.ant-modal-wrap, .ant-modal, [role="dialog"], [class*="modal"], [class*="dialog"], [class*="popup"]')
                    if await modal.count() > 0:
                        print("\n📦 检测到弹窗！正在分析弹窗内容...")
                        # 获取弹窗内的文字
                        modal_text = await modal.first.inner_text()
                        print(f"   弹窗内容: {modal_text[:200]}...")
                        
                        # 用 JS 直接获取弹窗中的按钮并点击（绕过 Playwright actionability 检查）
                        btn_texts = await page.evaluate("""
                        () => {
                            const modal = document.querySelector('.ant-modal-wrap, .ant-modal, [role="dialog"]');
                            if (!modal) return [];
                            const btns = modal.querySelectorAll('button');
                            return Array.from(btns).map((b, i) => ({index: i, text: b.textContent.trim()}));
                        }
                        """)
                        if btn_texts:
                            print(f"   弹窗中有 {len(btn_texts)} 个按钮:")
                            for b in btn_texts:
                                print(f"   [{b['index']}] {b['text']}")
                            
                            btn_choice = input("   输入按钮编号点击（或 's' 跳过弹窗）: ").strip()
                            if btn_choice.isdigit():
                                idx = int(btn_choice)
                                # 用 JS 原生 click 绕过所有遮罩检查
                                await page.evaluate(f"""
                                () => {{
                                    const modal = document.querySelector('.ant-modal-wrap, .ant-modal, [role="dialog"]');
                                    if (modal) {{
                                        const btns = modal.querySelectorAll('button');
                                        if (btns[{idx}]) btns[{idx}].click();
                                    }}
                                }}
                                """)
                                await asyncio.sleep(3)
                        
                        # 检查弹窗中是否有表单
                        modal_inputs = modal.first.locator('input, select, textarea, [role="combobox"]')
                        if await modal_inputs.count() > 0:
                            print(f"   弹窗中有 {await modal_inputs.count()} 个表单元素，将在下一步分析填写")

                    # 等待页面变化
                    try:
                        await page.wait_for_load_state('networkidle', timeout=5000)
                    except:
                        pass
                    await asyncio.sleep(2)

            # 循环处理多页表单
            page_num = 1
            while True:
                print(f"\n📋 Step 2.{page_num}: 分析页面结构（第 {page_num} 页）...")
                
                # 获取页面结构
                elements_json = await get_page_structure(page)
                page_text = await get_page_text_snapshot(page)
                
                elements = json.loads(elements_json)
                print(f"   发现 {len(elements)} 个可交互元素")
                
                if len(elements) == 0:
                    print("   未检测到可交互元素。")
                    print("\n   当前页面文字摘要:")
                    print(f"   {page_text[:300]}...")
                    choice = input("\n   输入 'w' 等待5秒重试，输入 'm' 手动输入操作，输入 'q' 退出: ").strip().lower()
                    if choice == 'w':
                        await asyncio.sleep(5)
                        continue
                    elif choice == 'm':
                        manual_selector = input("   输入要点击的按钮文字: ").strip()
                        if manual_selector:
                            btn = page.locator(f'button:has-text("{manual_selector}"), a:has-text("{manual_selector}"), span:has-text("{manual_selector}")')
                            if await btn.count() > 0:
                                await btn.first.click()
                                await asyncio.sleep(3)
                                continue
                    else:
                        break
                    continue

                # 显示检测到的元素
                for el in elements[:15]:  # 最多显示15个
                    label = el.get('label', '') or el.get('placeholder', '') or el.get('name', '') or el.get('id', '')
                    print(f"   [{el['index']}] {label} ({el['tag']}/{el['type']})")
                if len(elements) > 15:
                    print(f"   ... 还有 {len(elements) - 15} 个元素")

                # Step 3: LLM 分析
                print(f"\n🧠 Step 3.{page_num}: LLM 分析页面并生成填写方案...")
                prompt = build_analysis_prompt(elements_json, page_text, user_profile)
                result = call_llm_for_analysis(prompt, api_key=api_key, model=args.model)
                
                page_desc = result.get('page_description', '未知页面')
                actions = result.get('actions', [])
                fill_count = sum(1 for a in actions if a.get('method') not in ('skip', 'upload'))
                
                print(f"   📄 页面: {page_desc}")
                print(f"   📝 将填写 {fill_count} 个字段")

                if fill_count == 0:
                    print("   没有需要填写的字段。")
                    choice = input("   输入 'n' 下一步，输入 'q' 退出: ").strip().lower()
                    if choice == 'q':
                        break
                    # 尝试找下一步按钮
                    next_btn = page.locator('button:has-text("下一步"), button:has-text("Next"), button:has-text("继续"), button:has-text("保存")')
                    if await next_btn.count() > 0:
                        await next_btn.first.click()
                        await asyncio.sleep(3)
                        page_num += 1
                        continue
                    break

                # Step 4: 执行填写
                print(f"\n✍️  Step 4.{page_num}: 开始自动填充...")
                await execute_actions(page, actions)

                # Step 5: 截图确认
                print(f"\n📸 Step 5.{page_num}: 截图确认...")
                result = await screenshot_and_confirm(page, f"page_{page_num}")
                
                if result == 'n':
                    print("⏹️  已取消。浏览器保持打开。")
                    input("按 Enter 关闭浏览器...")
                    break
                elif result == 'r':
                    continue

                # 检查下一步
                next_btn = page.locator('button:has-text("下一步"), button:has-text("Next"), button:has-text("继续"), button:has-text("保存"), button:has-text("提交")')
                if await next_btn.count() > 0:
                    btn_text = await next_btn.first.inner_text()
                    print(f"\n➡️  检测到按钮: 「{btn_text}」")
                    if '提交' in btn_text:
                        print("   ⚠️  这是提交按钮！请你手动检查后决定是否提交。")
                        input("   按 Enter 关闭浏览器...")
                        break
                    choice = input(f"   输入 'y' 点击「{btn_text}」，输入 'n' 停在这里: ").strip().lower()
                    if choice == 'y':
                        await next_btn.first.click()
                        await asyncio.sleep(3)
                        try:
                            await page.wait_for_load_state('networkidle', timeout=5000)
                        except:
                            pass
                        page_num += 1
                        continue

                print("\n✅ 填写完成！请在浏览器中检查后手动提交。")
                input("\n按 Enter 关闭浏览器...")
                break

        except Exception as e:
            print(f"\n❌ 出错了: {e}")
            import traceback
            traceback.print_exc()
            input("\n按 Enter 关闭浏览器...")
        finally:
            await context.close()
            if browser:
                await browser.close()

    print("\n👋 再见！祝春招顺利！")


if __name__ == '__main__':
    asyncio.run(main())
