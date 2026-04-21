# 카카오 낚시 단순반복

카카오톡 채팅방 입력칸에 `/낚시`를 반복 전송하는 단일 파일 매크로입니다.

## 파일

- `낚시_단순반복.py` : 본체
- `requirements.txt` : 필요한 모듈

## 설치

```bat
py -m pip install -r requirements.txt
```

## 실행

```bat
py 낚시_단순반복.py
```

실행하면 먼저 아래 입력을 받습니다.

```text
반복 횟수 입력 (0 또는 빈값 = 무한 반복):
```

- `0` 또는 빈값: 무한 반복
- `10`: 10번 성공하면 자동 정지
- `100`: 100번 성공하면 자동 정지

## 사용법

1. 반복 횟수를 입력한다
2. 카카오톡 채팅방을 연다
3. 입력칸 위에 마우스를 올린다
4. `F9`로 대상 창/입력 위치를 잡고 입력창을 클릭한다
5. `F10`으로 시작
6. `F10`으로 일시정지/재개
7. `F12`로 정지

## 단축키

- `F9` : 대상 창 + 입력 위치 지정
- `F10` : 시작 / 일시정지 / 재개
- `F12` : 정지

## 시간이나 명령어 바꾸고 싶으면

`낚시_단순반복.py` 상단 상수만 직접 바꾸면 됩니다.

- `DEFAULT_COMMAND` : 기본 명령어
- `REPEAT_DELAY_SECONDS` : 반복 딜레이
- `FOCUS_SETTLE_DELAY_SECONDS` : 창 포커스 후 대기
- `CLIPBOARD_DELAY_SECONDS` : 클립보드 반영 대기
- `INPUT_SETTLE_DELAY_SECONDS` : 클릭/붙여넣기 사이 대기

예:

```python
DEFAULT_COMMAND = '/낚시'
REPEAT_DELAY_SECONDS = 2.0
```

수정 후 저장하고 다시 실행하면 됩니다.

## 출력 파일

필요할 때만 아래 파일이 생깁니다.

- `.local/simple_repeat_summary.txt` : 종료 요약

상세 로그 파일은 기본적으로 남기지 않습니다.

## 문제 생기면

- `필수 모듈이 없습니다`가 뜨면 다시 설치:

```bat
py -m pip install -r requirements.txt
```

- 엉뚱한 위치가 잡히면 `F9`로 입력칸을 다시 정확히 지정
- 단축키가 안 먹으면 관리자 권한으로 실행
