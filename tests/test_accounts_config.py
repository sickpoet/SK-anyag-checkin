import json

from utils.config import extract_cookie_value, load_accounts_config

BASE_ACCOUNTS = [
	{'name': 'any主帐号', 'cookies': {'session': 'base-session'}, 'api_user': '11111'},
	{'name': 'agLD', 'provider': 'agentrouter', 'cookies': {'session': 'ld-session'}, 'api_user': '22222'},
	{'name': 'agGithub', 'cookies': {'session': 'stale-session'}, 'api_user': '33333'},
]

MLGB_ACCOUNT = {'name': 'mlgb7', 'provider': 'mlgb7', 'api_user': 'mlgb7', 'cookies': {'chatgpt2api_session': 'old'}}


def _set_env(monkeypatch, base=BASE_ACCOUNTS, extra=None):
	monkeypatch.setenv('ANYROUTER_ACCOUNTS', json.dumps(base))
	monkeypatch.delenv('MLGB7_COOKIE', raising=False)
	monkeypatch.delenv('ANY_COOKIE', raising=False)
	if extra is None:
		monkeypatch.delenv('ANYROUTER_ACCOUNTS_EXTRA', raising=False)
	else:
		monkeypatch.setenv('ANYROUTER_ACCOUNTS_EXTRA', json.dumps(extra))


def test_base_accounts_load_unchanged_without_extra(monkeypatch):
	_set_env(monkeypatch)

	accounts = load_accounts_config()

	assert accounts is not None
	assert [a.name for a in accounts] == ['any主帐号', 'agLD', 'agGithub']
	assert all(not a.has_login_credentials() for a in accounts)


def test_empty_extra_is_ignored(monkeypatch):
	_set_env(monkeypatch, extra=[])
	monkeypatch.setenv('ANYROUTER_ACCOUNTS_EXTRA', '   ')

	accounts = load_accounts_config()

	assert accounts is not None
	assert len(accounts) == 3


def test_extra_overrides_same_name_to_email_login(monkeypatch):
	_set_env(monkeypatch, extra=[{'name': 'agGithub', 'email': 'a@b.com', 'password': 'pw'}])

	accounts = load_accounts_config()

	assert accounts is not None
	assert [a.name for a in accounts] == ['any主帐号', 'agLD', 'agGithub']

	ag_github = accounts[2]
	assert ag_github.email == 'a@b.com'
	assert ag_github.password == 'pw'
	assert ag_github.has_login_credentials() is True

	# 其它账号不受影响
	assert accounts[0].cookies == {'session': 'base-session'}
	assert accounts[1].cookies == {'session': 'ld-session'}


def test_override_is_field_level_and_keeps_provider(monkeypatch):
	_set_env(
		monkeypatch,
		extra=[{'name': 'agLD', 'email': 'ld@b.com', 'password': 'pw'}],
	)

	accounts = load_accounts_config()

	assert accounts is not None
	ag_ld = accounts[1]
	assert ag_ld.provider == 'agentrouter'  # 未被覆盖的字段保留
	assert ag_ld.email == 'ld@b.com'
	assert ag_ld.api_user == '22222'


def test_partial_override_of_existing_account_is_allowed(monkeypatch):
	_set_env(monkeypatch, extra=[{'name': 'agGithub', 'api_user': '99999'}])

	accounts = load_accounts_config()

	assert accounts is not None
	assert len(accounts) == 3
	assert accounts[2].api_user == '99999'
	assert accounts[2].cookies == {'session': 'stale-session'}


def test_extra_appends_new_account(monkeypatch):
	_set_env(
		monkeypatch,
		extra=[{'name': 'agNew', 'provider': 'agentrouter', 'email': 'n@b.com', 'password': 'pw'}],
	)

	accounts = load_accounts_config()

	assert accounts is not None
	assert [a.name for a in accounts] == ['any主帐号', 'agLD', 'agGithub', 'agNew']
	assert accounts[3].provider == 'agentrouter'


def test_extra_without_credentials_for_unknown_account_fails(monkeypatch):
	_set_env(monkeypatch, extra=[{'name': 'ghost', 'api_user': '1'}])

	assert load_accounts_config() is None


def test_invalid_extra_json_fails_loudly(monkeypatch):
	_set_env(monkeypatch)
	monkeypatch.setenv('ANYROUTER_ACCOUNTS_EXTRA', '[{"name": "bad",}]')

	assert load_accounts_config() is None


def test_missing_base_env_returns_none(monkeypatch):
	monkeypatch.delenv('ANYROUTER_ACCOUNTS', raising=False)
	monkeypatch.setenv('ANYROUTER_ACCOUNTS_EXTRA', json.dumps([{'name': 'x', 'cookies': {'a': 'b'}}]))

	assert load_accounts_config() is None


# --- MLGB7_COOKIE：把 mlgb7 的会话 cookie 拆成独立 secret ------------------------


def test_mlgb7_cookie_overrides_extra_value(monkeypatch):
	"""换 cookie 时只改 MLGB7_COOKIE，EXTRA 里留着旧值也不影响签到。"""
	_set_env(monkeypatch, extra=[MLGB_ACCOUNT])
	monkeypatch.setenv('MLGB7_COOKIE', 'fresh-session')

	accounts = load_accounts_config()

	assert accounts is not None
	mlgb = accounts[3]
	assert mlgb.provider == 'mlgb7'
	assert mlgb.cookies == {'chatgpt2api_session': 'fresh-session'}


def test_mlgb7_cookie_unset_keeps_extra_cookies(monkeypatch):
	_set_env(monkeypatch, extra=[MLGB_ACCOUNT])

	accounts = load_accounts_config()

	assert accounts is not None
	assert accounts[3].cookies == {'chatgpt2api_session': 'old'}


def test_mlgb7_cookie_does_not_touch_other_accounts(monkeypatch):
	_set_env(monkeypatch, extra=[MLGB_ACCOUNT])
	monkeypatch.setenv('MLGB7_COOKIE', 'fresh-session')

	accounts = load_accounts_config()

	assert accounts is not None
	assert accounts[0].cookies == {'session': 'base-session'}
	assert accounts[1].cookies == {'session': 'ld-session'}
	assert accounts[2].cookies == {'session': 'stale-session'}


def test_mlgb7_cookie_accepts_dotcom_browser_plugin_json(monkeypatch):
	"""插件"复制 cookie"给的是整段 JSON，原样塞进 secret 也要能用。"""
	_set_env(monkeypatch, extra=[MLGB_ACCOUNT])
	monkeypatch.setenv(
		'MLGB7_COOKIE',
		json.dumps(
			[
				{
					'domain': 'image.mlgb7.com',
					'hostOnly': True,
					'httpOnly': True,
					'name': 'chatgpt2api_session',
					'path': '/',
					'value': 'from-json',
				}
			]
		),
	)

	accounts = load_accounts_config()

	assert accounts is not None
	assert accounts[3].cookies == {'chatgpt2api_session': 'from-json'}


def test_mlgb7_cookie_env_unused_when_no_mlgb7_account(monkeypatch):
	_set_env(monkeypatch)
	monkeypatch.setenv('MLGB7_COOKIE', 'fresh-session')

	accounts = load_accounts_config()

	assert accounts is not None
	assert len(accounts) == 3


def test_any_cookie_overrides_only_the_named_account(monkeypatch):
	"""ANY_COOKIE 只改 any主帐号：agGithub 同样是 anyrouter provider，不能被连带覆盖。"""
	_set_env(monkeypatch)
	monkeypatch.setenv('ANY_COOKIE', 'fresh-any-session')

	accounts = load_accounts_config()

	assert accounts is not None
	assert accounts[0].cookies == {'session': 'fresh-any-session'}
	assert accounts[2].cookies == {'session': 'stale-session'}


def test_any_cookie_unset_keeps_extra_cookies(monkeypatch):
	_set_env(monkeypatch)

	accounts = load_accounts_config()

	assert accounts is not None
	assert accounts[0].cookies == {'session': 'base-session'}


def test_any_cookie_accepts_name_value_and_plugin_json(monkeypatch):
	_set_env(monkeypatch)
	monkeypatch.setenv('ANY_COOKIE', 'session=pasted-value')
	assert load_accounts_config()[0].cookies == {'session': 'pasted-value'}

	monkeypatch.setenv(
		'ANY_COOKIE',
		json.dumps([{'domain': 'anyrouter.top', 'name': 'session', 'value': 'json-value', 'path': '/'}]),
	)
	assert load_accounts_config()[0].cookies == {'session': 'json-value'}


def test_any_cookie_env_unused_when_no_matching_account(monkeypatch):
	_set_env(monkeypatch, base=[BASE_ACCOUNTS[1]])
	monkeypatch.setenv('ANY_COOKIE', 'fresh-any-session')

	accounts = load_accounts_config()

	assert accounts is not None
	assert len(accounts) == 1
	assert accounts[0].cookies == {'session': 'ld-session'}


def test_extract_cookie_value_forms():
	assert extract_cookie_value('FZ76abc') == 'FZ76abc'
	assert extract_cookie_value('  FZ76abc  ') == 'FZ76abc'
	assert extract_cookie_value('chatgpt2api_session=FZ76abc') == 'FZ76abc'
	assert extract_cookie_value('[{"name":"chatgpt2api_session","value":"FZ76abc"}]') == 'FZ76abc'
	assert extract_cookie_value('') == ''


def test_extract_cookie_value_keeps_unrecognised_input():
	"""认不出来就原样返回，别把用户的值悄悄吃掉。"""
	assert extract_cookie_value('[{"name":"other","value":"x"}]') == '[{"name":"other","value":"x"}]'
	assert extract_cookie_value('[not json') == '[not json'
