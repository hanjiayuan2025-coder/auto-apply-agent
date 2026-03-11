#!/usr/bin/env python3
"""
春招网申自动填表 Agent - CLI 入口
用法: python run.py --url "https://campus.163.com/app/..." --profile user_profile.json

工作流程:
  1. 打开你的 Chrome 浏览器（使用你已登录的会话）
  2. 导航到目标网申页面
  3. 自动识别表单字段
  4. 用 LLM 做智能字段映射
  5. 自动填充（每页截图让你确认）
  6. 不会自动提交，最终提交由你手动操作
"""
import argparse
import asyncio
import json
import os
import sys
from pathlib import Path

# 添加当前目录到 path
sys.path.insert(0, str(Path(__file__).parent))

from form_filler import (
    extract_form_fields,
    build_llm_prompt,
    fill_form,
    screenshot_and_confirm,
    load_user_profile,
    call_llm_for_mapping
)
from playwright.async_api import async_playwright


async def main():
    parser = argparse.ArgumentParser(description='春招网申自动填表 Agent 🤖')
    parser.add_argument('--url', required=True, help='目标网申页面 URL')
    parser.add_argument('--profile', default='user_profile.json', help='用户信息 JSON 文件路径')
    parser.add_argument('--api-key', default=None, help='OpenAI API Key（也可设ENV: OPENAI_API_KEY）')
    parser.add_argument('--model', default='gpt-4o-mini', help='LLM 模型名称（默认 gpt-4o-mini，便宜够用）')
    parser.add_argument('--headless', action='store_true', help='无头模式（默认有头，方便观察）')
    parser.add_argument('--slow', type=int, default=100, help='操作间隔毫秒（默认100ms）')
    parser.add_argument('--chrome-path', default=None, help='Chrome 浏览器路径（如不指定则自动查找）')
    parser.add_argument('--user-data-dir', default=None, help='Chrome 用户数据目录（复用已登录状态）')
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
        print("⚠️  未设置 OpenAI API Key。请通过 --api-key 参数或 OPENAI_API_KEY 环境变量设置。")
        api_key = input("请输入你的 OpenAI API Key: ").strip()
        if not api_key:
            print("❌ 需要 API Key 才能使用 LLM 字段映射功能")
            sys.exit(1)

    # 查找 Chrome 浏览器路径
    chrome_path = args.chrome_path
    if not chrome_path:
        possible_paths = [
            '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
            '/Applications/Chromium.app/Contents/MacOS/Chromium',
            '/usr/bin/google-chrome',
            '/usr/bin/chromium-browser',
        ]
        for p in possible_paths:
            if os.path.exists(p):
                chrome_path = p
                break

    print(f"\n🚀 春招网申自动填表 Agent 启动")
    print(f"   目标: {args.url}")
    print(f"   模型: {args.model}")
    print(f"   浏览器: {chrome_path or 'Playwright 内置 Chromium'}")
    print("=" * 60)

    async with async_playwright() as p:
        # 启动浏览器
        launch_args = {
            'headless': args.headless,
            'slow_mo': args.slow,
        }
        
        if chrome_path:
            launch_args['executable_path'] = chrome_path
        
        # 如果提供了用户数据目录（复用已登录状态）
        if args.user_data_dir:
            context = await p.chromium.launch_persistent_context(
                args.user_data_dir,
                **launch_args,
                viewport={'width': 1280, 'height': 900}
            )
            page = context.pages[0] if context.pages else await context.new_page()
        else:
            browser = await p.chromium.launch(**launch_args)
            context = await browser.new_context(
                viewport={'width': 1280, 'height': 900},
                locale='zh-CN'
            )
            page = await context.new_page()

        try:
            # Step 1: 导航到目标页面
            print("\n📄 Step 1: 打开目标页面...")
            await page.goto(args.url, wait_until='networkidle', timeout=30000)
            await asyncio.sleep(2)  # 等待 React/SPA 渲染
            
            title = await page.title()
            print(f"   页面标题: {title}")
            
            # 检查是否需要登录
            page_content = await page.content()
            if '登录' in await page.inner_text('body'):
                print("\n⚠️  检测到页面可能需要登录。")
                print("   请在打开的浏览器窗口中手动登录，完成后按 Enter 继续...")
                input("   [按 Enter 继续]")
                await asyncio.sleep(2)

            # 检查是否需要先点击"申请/投递"按钮
            apply_btn = page.locator('button:has-text("申请"), button:has-text("投递"), a:has-text("申请"), a:has-text("投递"), button:has-text("Apply")')
            if await apply_btn.count() > 0:
                print("\n🔘 检测到「投递/申请」按钮，是否点击进入申请表？")
                choice = input("   输入 'y' 点击进入，输入 'n' 跳过: ").strip().lower()
                if choice == 'y':
                    await apply_btn.first.click()
                    await asyncio.sleep(3)
                    await page.wait_for_load_state('networkidle')

            # 循环处理多页表单
            page_num = 1
            while True:
                print(f"\n📋 Step 2.{page_num}: 提取表单字段（第 {page_num} 页）...")
                form_fields = await extract_form_fields(page)
                
                if not form_fields:
                    print("   未检测到可填写的表单字段。")
                    print("   可能原因：页面还在加载 / 需要点击某个按钮进入表单 / 已经填完了")
                    choice = input("   输入 'w' 等待5秒后重试，输入 's' 跳过，输入 'q' 退出: ").strip().lower()
                    if choice == 'w':
                        await asyncio.sleep(5)
                        continue
                    elif choice == 'q':
                        break
                    else:
                        break
                
                print(f"   找到 {len(form_fields)} 个可填写字段:")
                for i, f in enumerate(form_fields):
                    label = f.get('label', '') or f.get('placeholder', '') or f.get('name', '') or f.get('id', '')
                    print(f"   [{i}] {label} ({f['tag']}/{f['type']})")

                # Step 3: LLM 字段映射
                print(f"\n🧠 Step 3.{page_num}: LLM 智能字段映射中...")
                prompt = build_llm_prompt(form_fields, user_profile)
                mappings = call_llm_for_mapping(prompt, api_key=api_key, model=args.model)
                
                fill_count = sum(1 for m in mappings if m['action'] != 'skip')
                skip_count = sum(1 for m in mappings if m['action'] == 'skip')
                print(f"   映射完成: {fill_count} 个字段将被填写, {skip_count} 个字段跳过")

                # Step 4: 自动填充
                print(f"\n✍️  Step 4.{page_num}: 开始自动填充...")
                await fill_form(page, mappings, form_fields)

                # Step 5: 截图确认
                print(f"\n📸 Step 5.{page_num}: 截图确认...")
                result = await screenshot_and_confirm(page, f"page_{page_num}")
                
                if result == 'n':
                    print("⏹️  已取消。浏览器保持打开，你可以手动修改。")
                    input("按 Enter 关闭浏览器...")
                    break
                elif result == 'r':
                    print("🔄 重新填写...")
                    continue

                # 检查是否有"下一步"按钮
                next_btn = page.locator('button:has-text("下一步"), button:has-text("Next"), button:has-text("继续"), a:has-text("下一步")')
                if await next_btn.count() > 0:
                    print("\n➡️  检测到「下一步」按钮")
                    choice = input("   输入 'y' 点击下一步，输入 'n' 停在这里: ").strip().lower()
                    if choice == 'y':
                        await next_btn.first.click()
                        await asyncio.sleep(3)
                        await page.wait_for_load_state('networkidle')
                        page_num += 1
                        continue
                
                print("\n✅ 填写完成！")
                print("⚠️  请在浏览器中仔细检查所有字段，确认无误后手动点击提交。")
                print("   脚本不会自动提交表单。")
                input("\n按 Enter 关闭浏览器...")
                break

        except Exception as e:
            print(f"\n❌ 出错了: {e}")
            import traceback
            traceback.print_exc()
            input("\n按 Enter 关闭浏览器...")
        
        finally:
            await context.close()
            if not args.user_data_dir:
                await browser.close()

    print("\n👋 再见！祝春招顺利！")


if __name__ == '__main__':
    asyncio.run(main())
