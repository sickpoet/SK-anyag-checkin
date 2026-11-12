"""CDN 挑战识别与浏览器降级判定。

anyrouter.top 现在挂在阿里云 ESA 后面：客户端 TLS 指纹不像浏览器时，/api 请求会被
`X-Tengine-Error: denied by http_custom` 拒掉，状态码仍然是 200，body 换成
`acw_sc__v2` 的 JS 挑战脚本。httpx 拿到这种响应只会报 "响应不是有效 JSON"，
指不到真正的原因，也就不会降级到浏览器。这组测试锁住识别逻辑。
"""

import httpx

from checkin import (
	STATUS_ALREADY_CHECKED,
	STATUS_CHECKED_IN,
	STATUS_FAILED,
	_interpret_check_in_payload,
	_interpret_user_info_payload,
	_looks_like_waf_challenge,
)

ESA_CHALLENGE_HTML = (
	"<html><script>var arg1='5550FA3042046B51C8C0BF7552CBFC2404AE5FE3';(function(a,c){"
	'var G=a0j,d=a();while(!![]){try{var e=-parseInt(G(0x117))/0x1;}catch(f){}}}(a0i,0x760bf))</script></html>'
)

USER_INFO_JSON = (
	'{"success":true,"data":{"quota":733040000,"used_quota":142034000,"group":"default"}}'
)


def _response(body: str, content_type: str, status_code: int = 200) -> httpx.Response:
	return httpx.Response(status_code, headers={'content-type': content_type}, text=body)


def test_esa_challenge_detected_despite_http_200():
	"""状态码 200 但 body 是挑战脚本 —— 这是最坑的一种，必须认出来。"""
	response = _response(ESA_CHALLENGE_HTML, 'text/html; charset=utf-8')

	assert response.status_code == 200
	assert _looks_like_waf_challenge(response) is True


def test_business_json_is_not_a_challenge():
	response = _response(USER_INFO_JSON, 'application/json; charset=utf-8')

	assert _looks_like_waf_challenge(response) is False


def test_json_content_type_with_html_body_is_not_a_challenge():
	"""只按 content-type 判断会漏掉伪装成 JSON 的 HTML，所以再看 body。"""
	response = _response(ESA_CHALLENGE_HTML, 'application/json; charset=utf-8')

	# content-type 是 JSON 时不由这里判定，交给 json 解析报错，避免误报
	assert _looks_like_waf_challenge(response) is False


def test_user_info_payload_success():
	result = _interpret_user_info_payload(200, USER_INFO_JSON)

	assert result['success'] is True
	assert result['quota'] == 1466.08
	assert result['used_quota'] == 284.07
	assert result['group'] == 'default'


def test_user_info_payload_unauthorized():
	result = _interpret_user_info_payload(
		401, '{"message":"无权进行此操作，未登录且未提供 access token","success":false}'
	)

	assert result['success'] is False
	assert 'HTTP 401' in result['error']


def test_user_info_payload_challenge_html_is_not_success():
	result = _interpret_user_info_payload(200, ESA_CHALLENGE_HTML)

	assert result['success'] is False


def test_check_in_payload_success():
	result = _interpret_check_in_payload(200, '{"success":true,"message":"签到成功"}', 'any主帐号')

	assert result.status == STATUS_CHECKED_IN


def test_check_in_payload_already_checked():
	result = _interpret_check_in_payload(200, '{"success":false,"message":"今日已签到"}', 'any主帐号')

	assert result.status == STATUS_ALREADY_CHECKED


def test_check_in_payload_challenge_html_fails():
	result = _interpret_check_in_payload(200, ESA_CHALLENGE_HTML, 'any主帐号')

	assert result.status == STATUS_FAILED
	assert result.message == '响应不是有效 JSON'
