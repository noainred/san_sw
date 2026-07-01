"""yapen_monitor — 야펜(yapen) 외부예약 페이지 계약가능 감시기.

특정 야펜 예약 위젯 페이지(`rev.yapen.co.kr/external/set`)를 주기적으로 점검해서
지정한 동(예: A·B·C·D·F)이 '계약 가능(예약 가능)' 상태가 되면 Slack으로 알린다.

구성:
- config   : 실행 설정(env/CLI)
- parser   : HTML → 동별 예약가능 여부(정규식 기반, 튜닝 가능)
- notify   : Slack Incoming Webhook 발송
- monitor  : 페이지 fetch + 상태 저장 + 루프 오케스트레이션
"""

__version__ = "0.1.0"
