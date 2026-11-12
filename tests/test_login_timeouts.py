"""登录页各阶段超时的取值规则。

这块出过一次静默失效：`_wait_for_login_shell` 的上限从 60 秒提到 90 秒，
但调用方 `attempt_timeout` 早被 `min(timeout_ms, 60_000)` 截成 60 秒，
传进去再取 min 还是 60 秒 —— 改动等于没做，而日志上看不出任何异常，
只表现为「登录页又是没渲染」。所以把导航超时和 shell 超时分开钉死。
"""

import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from utils import browser


def _make_page():
	page = MagicMock()
	page.goto = AsyncMock()
	page.reload = AsyncMock()
	page.evaluate = AsyncMock(return_value=True)
	page.wait_for_function = AsyncMock()
	page.wait_for_load_state = AsyncMock()
	page.screenshot = AsyncMock()
	return page


def _stub_navigation_side_effects(monkeypatch):
	monkeypatch.setattr(browser, 'dismiss_popups', AsyncMock(return_value=0))
	monkeypatch.setattr(browser, '_settle_page', AsyncMock())
	monkeypatch.setattr(browser, 'wait_for_site_ready', AsyncMock())
	monkeypatch.setattr(browser, '_log_login_page_state', AsyncMock())
	monkeypatch.setattr(browser, 'save_login_screenshot', AsyncMock())


async def test_shell_wait_honours_full_two_minutes():
	page = _make_page()

	assert await browser._wait_for_login_shell(page, 120_000) is True

	# 关键回归：workflow 配的 120000 必须原样透到 wait_for_function，
	# 不能再被 60 秒或 90 秒的天花板砍掉。
	assert page.wait_for_function.await_args.kwargs['timeout'] == 120_000


async def test_shell_wait_keeps_smaller_callers_value():
	page = _make_page()

	await browser._wait_for_login_shell(page, 45_000)

	assert page.wait_for_function.await_args.kwargs['timeout'] == 45_000


async def test_shell_wait_caps_runaway_values():
	page = _make_page()

	await browser._wait_for_login_shell(page, 600_000)

	# 单张号最坏 3 次 attempt，若放任调用方传大值会拖垮整个 job。
	assert page.wait_for_function.await_args.kwargs['timeout'] == browser.LOGIN_SHELL_TIMEOUT_MS


async def test_navigation_uses_its_own_timeout(monkeypatch):
	page = _make_page()
	_stub_navigation_side_effects(monkeypatch)
	monkeypatch.setattr(browser, '_wait_for_login_shell', AsyncMock(return_value=True))

	await browser.navigate_login_page(page, 'https://agentrouter.org/login', 120_000)

	# 导航不该跟着 shell 一起放到 2 分钟：卡住就是节点不通，早失败早重试。
	timeouts = {call.kwargs['timeout'] for call in page.goto.await_args_list}
	assert timeouts == {browser.NAV_TIMEOUT_MS}
	assert browser.NAV_TIMEOUT_MS < browser.LOGIN_SHELL_TIMEOUT_MS


async def test_navigation_passes_wait_budget_not_nav_timeout(monkeypatch):
	page = _make_page()
	_stub_navigation_side_effects(monkeypatch)
	shell_wait = AsyncMock(return_value=True)
	monkeypatch.setattr(browser, '_wait_for_login_shell', shell_wait)

	await browser.navigate_login_page(page, 'https://agentrouter.org/login', 120_000)

	# 这里传错过一次：传 attempt_timeout 会让 shell 等待退回 90 秒。
	assert shell_wait.await_args.args[1] == 120_000


async def test_navigation_reload_uses_nav_timeout(monkeypatch):
	page = _make_page()
	_stub_navigation_side_effects(monkeypatch)
	attempts = []

	async def shell_never_ready(_page, _timeout_ms):
		attempts.append(1)
		return False

	monkeypatch.setattr(browser, '_wait_for_login_shell', shell_never_ready)
	monkeypatch.setattr(browser.asyncio, 'sleep', AsyncMock())

	with __import__('pytest').raises(TimeoutError):
		await browser.navigate_login_page(page, 'https://agentrouter.org/login', 120_000)

	assert len(attempts) == 3
	reload_timeouts = {call.kwargs['timeout'] for call in page.reload.await_args_list}
	assert reload_timeouts == {browser.NAV_TIMEOUT_MS}
