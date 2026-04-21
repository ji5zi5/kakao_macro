from __future__ import annotations

from dataclasses import dataclass
import importlib.util
import sys
import time
import traceback
import types
from pathlib import Path
from threading import Event, Thread
from time import sleep
from typing import Callable

ROOT = Path(__file__).resolve().parent
LOCAL_STATE_DIR = ROOT / '.local'
LOG_PATH = LOCAL_STATE_DIR / 'simple_repeat.log'
SUMMARY_PATH = LOCAL_STATE_DIR / 'simple_repeat_summary.txt'

REPEAT_DELAY_SECONDS = 2.0
FOCUS_SETTLE_DELAY_SECONDS = 0.1
FOREGROUND_RETRY_DELAY_SECONDS = 0.15
CLIPBOARD_DELAY_SECONDS = 0.3
INPUT_SETTLE_DELAY_SECONDS = 0.05
DEFAULT_COMMAND = '/낚시'


def _sync_module_globals() -> None:
    module = sys.modules.get(__name__)
    if module is None:
        module = types.ModuleType(__name__)
        sys.modules[__name__] = module
    module.__dict__.update(globals())


_sync_module_globals()


# 출력/요약


def append_log(message: str) -> None:
    timestamp = time.strftime('%H:%M:%S')
    line = f'[{timestamp}] {message}'
    print(line)


def write_summary(message: str) -> None:
    SUMMARY_PATH.parent.mkdir(parents=True, exist_ok=True)
    SUMMARY_PATH.write_text(message + '\n', encoding='utf-8')


def report_startup_failure(exc: BaseException) -> int:
    detail = ''.join(traceback.format_exception(type(exc), exc, exc.__traceback__)).strip()
    append_log('[치명적 오류] 단순반복 프로그램 시작에 실패했습니다.')
    for line in detail.splitlines():
        append_log(line)
    write_summary(f'시작 실패: {exc}')
    return 1


# 입력/클립보드

def _default_ui():
    import pyautogui  # type: ignore

    pyautogui.FAILSAFE = True
    return pyautogui


def read_clipboard_text() -> str:
    try:
        import win32clipboard  # type: ignore
    except ImportError:
        return ''

    try:
        win32clipboard.OpenClipboard()
        data = win32clipboard.GetClipboardData()
        return str(data).strip()
    except Exception:
        return ''
    finally:
        try:
            win32clipboard.CloseClipboard()
        except Exception:
            pass


def write_clipboard_text(text: str) -> bool:
    try:
        import win32clipboard  # type: ignore
        import win32con  # type: ignore
    except ImportError:
        return False

    try:
        win32clipboard.OpenClipboard()
        win32clipboard.EmptyClipboard()
        win32clipboard.SetClipboardData(win32con.CF_UNICODETEXT, text)
        return True
    except Exception:
        return False
    finally:
        try:
            win32clipboard.CloseClipboard()
        except Exception:
            pass


def extract_wrapper_texts_with_fallback(wrapper, *, read_clipboard=read_clipboard_text) -> list[str]:
    texts = [text for text in wrapper.texts() if text]
    if texts:
        return texts
    if hasattr(wrapper, 'click_input'):
        try:
            wrapper.click_input()
        except Exception:
            pass
    wrapper.set_focus()
    wrapper.type_keys('^a', set_foreground=True)
    wrapper.type_keys('^c', set_foreground=True)
    clipboard_text = read_clipboard().strip()
    return [clipboard_text] if clipboard_text else []


def extract_drag_selected_text(
    *,
    anchor_x: int,
    start_y: int,
    end_y: int,
    restore_y: int | None = None,
    read_clipboard=read_clipboard_text,
    ui=None,
) -> list[str]:
    ui_backend = ui or _default_ui()
    ui_backend.moveTo(anchor_x, start_y)
    ui_backend.mouseDown()
    ui_backend.moveTo(anchor_x, end_y, duration=0.35)
    ui_backend.mouseUp()
    ui_backend.hotkey('ctrl', 'c')
    ui_backend.click(anchor_x, end_y if restore_y is None else restore_y)
    clipboard_text = read_clipboard().strip()
    return [clipboard_text] if clipboard_text else []


def _send_double_enter(
    *,
    paste,
    press_enter,
    input_settle_delay: float,
) -> None:
    paste()
    time.sleep(input_settle_delay)
    press_enter()
    time.sleep(input_settle_delay)
    press_enter()


def _run_clipboard_send_loop(
    *,
    text: str,
    attempts: int,
    clipboard_delay: float,
    read_clipboard,
    write_clipboard,
    on_match,
    on_mismatch=None,
) -> bool:
    write_clipboard('')
    for attempt in range(1, attempts + 1):
        write_clipboard(text)
        time.sleep(clipboard_delay)
        if read_clipboard().strip() == text:
            on_match(attempt)
            return True
        if on_mismatch is not None:
            on_mismatch(attempt)
        write_clipboard('')
    return False


def send_text_via_clipboard(
    wrapper,
    text: str,
    *,
    read_clipboard=read_clipboard_text,
    write_clipboard=write_clipboard_text,
    attempts: int = 5,
    clipboard_delay: float = CLIPBOARD_DELAY_SECONDS,
    input_settle_delay: float = INPUT_SETTLE_DELAY_SECONDS,
) -> bool:
    if hasattr(wrapper, 'click_input'):
        try:
            wrapper.click_input()
        except Exception:
            pass
    wrapper.set_focus()
    time.sleep(input_settle_delay)
    wrapper.type_keys('^a', set_foreground=True)
    time.sleep(input_settle_delay)
    wrapper.type_keys('{BACKSPACE}', set_foreground=True)

    return _run_clipboard_send_loop(
        text=text,
        attempts=attempts,
        clipboard_delay=clipboard_delay,
        read_clipboard=read_clipboard,
        write_clipboard=write_clipboard,
        on_match=lambda _attempt: _send_double_enter(
            paste=lambda: wrapper.type_keys('^v', set_foreground=True),
            press_enter=lambda: wrapper.type_keys('{ENTER}', set_foreground=True),
            input_settle_delay=input_settle_delay,
        ),
    )


def send_text_at_point(
    *,
    x: int,
    y: int,
    text: str,
    ui=None,
    read_clipboard=read_clipboard_text,
    write_clipboard=write_clipboard_text,
    attempts: int = 5,
    clipboard_delay: float = CLIPBOARD_DELAY_SECONDS,
    input_settle_delay: float = INPUT_SETTLE_DELAY_SECONDS,
    event_sink=None,
) -> bool:
    def emit(message: str) -> None:
        if event_sink is not None:
            event_sink(message)

    ui_backend = ui or _default_ui()
    emit(f'입력창 클릭: ({x}, {y})')
    ui_backend.click(x, y)
    time.sleep(input_settle_delay)
    emit('입력창 전체 선택 시도')
    ui_backend.hotkey('ctrl', 'a')
    time.sleep(input_settle_delay)
    emit('입력창 비우기')
    ui_backend.press('backspace')

    sent = _run_clipboard_send_loop(
        text=text,
        attempts=attempts,
        clipboard_delay=clipboard_delay,
        read_clipboard=read_clipboard,
        write_clipboard=write_clipboard,
        on_match=lambda attempt: (
            emit(f'클립보드 확인 성공 ({attempt}/{attempts})'),
            _send_double_enter(
                paste=lambda: ui_backend.hotkey('ctrl', 'v'),
                press_enter=lambda: ui_backend.press('enter'),
                input_settle_delay=input_settle_delay,
            ),
            emit(f'{text} 전송 완료'),
        ),
        on_mismatch=lambda attempt: emit(f'클립보드 불일치 ({attempt}/{attempts})'),
    )
    if not sent:
        emit(f'{text} 전송 실패')
    return sent


# 반복 실행

@dataclass(slots=True)
class RepeatConfig:
    delay_seconds: float = REPEAT_DELAY_SECONDS
    focus_settle_seconds: float = FOCUS_SETTLE_DELAY_SECONDS
    command: str = DEFAULT_COMMAND
    max_success_count: int | None = None


@dataclass(slots=True)
class RepeatTarget:
    window_handle: int
    window_title: str
    input_x: int
    input_y: int


class SimpleRepeatRuntime:
    def __init__(self, event_sink=None, window_api=None, text_sender=None) -> None:
        self.event_sink = event_sink
        self.window_api = window_api
        self.text_sender = text_sender

    def _window_api(self):
        if self.window_api is not None:
            return self.window_api
        import win32gui  # type: ignore

        return win32gui

    def _describe_foreground(self, win32gui, handle: int | None = None) -> str:
        if handle is None:
            handle = getattr(win32gui, 'GetForegroundWindow', lambda: 0)()
        title = ''
        if hasattr(win32gui, 'GetWindowText'):
            try:
                title = win32gui.GetWindowText(handle)
            except Exception:
                title = ''
        return f"현재 foreground: HWND={handle} / 제목={title or '알 수 없음'}"

    def activate_window(self, handle: int) -> None:
        win32gui = self._window_api()
        if self.event_sink is not None:
            self.event_sink(f'[창] HWND {handle} 활성화 시도')
        current_handle = None
        for _ in range(5):
            win32gui.ShowWindow(handle, 5)
            if hasattr(win32gui, 'BringWindowToTop'):
                win32gui.BringWindowToTop(handle)
            if hasattr(win32gui, 'SetForegroundWindow'):
                win32gui.SetForegroundWindow(handle)
            if hasattr(win32gui, 'SetActiveWindow'):
                win32gui.SetActiveWindow(handle)
            sleep(FOREGROUND_RETRY_DELAY_SECONDS)
            current_handle = getattr(win32gui, 'GetForegroundWindow', lambda: handle)()
            if current_handle == handle:
                if self.event_sink is not None:
                    self.event_sink(f'[창] foreground 확인 성공: {self._describe_foreground(win32gui, current_handle)}')
                return
        if self.event_sink is not None:
            self.event_sink(f'[창] 포커스 실패: {self._describe_foreground(win32gui, current_handle)}')
        raise RuntimeError('대상 창 포커스를 잡지 못했습니다.')

    def send_text(self, x: int, y: int, text: str) -> bool:
        if self.text_sender is not None:
            return self.text_sender(x, y, text)
        return send_text_at_point(
            x=x,
            y=y,
            text=text,
            event_sink=self.event_sink,
            clipboard_delay=CLIPBOARD_DELAY_SECONDS,
            input_settle_delay=INPUT_SETTLE_DELAY_SECONDS,
        )


class SimpleRepeatController:
    def __init__(self, *, runtime, config: RepeatConfig, event_sink: Callable[[str], None] | None = None) -> None:
        self.runtime = runtime
        self.config = config
        self.event_sink = event_sink
        self.target: RepeatTarget | None = None
        self.running = False
        self.shutdown_requested = False
        self.attempt_count = 0
        self.success_count = 0
        self.failure_count = 0
        self.last_status = '아직 전송 시도가 없습니다.'
        self._stop_event = Event()
        self._thread: Thread | None = None

    def _emit(self, message: str) -> None:
        if self.event_sink is not None:
            self.event_sink(message)

    def set_target(self, target: RepeatTarget) -> None:
        self.target = target
        self.last_status = f'대상 지정 완료: {target.window_title}'
        self._emit(f'[F9] 대상 지정: {target.window_title} / HWND={target.window_handle} / ({target.input_x}, {target.input_y})')

    def toggle_running(self) -> bool:
        self.running = not self.running
        return self.running

    def send_once(self) -> bool:
        if self.target is None:
            self.last_status = '대상 없음'
            self._emit('[전송] 대상 창이 없어 전송하지 못했습니다.')
            return False
        self.attempt_count += 1
        self._emit(f'[전송] 대상 활성화 시도: HWND={self.target.window_handle} / ({self.target.input_x}, {self.target.input_y})')
        try:
            self.runtime.activate_window(self.target.window_handle)
        except Exception as exc:
            self.failure_count += 1
            self.last_status = str(exc)
            self._emit(f'[전송] 포커스 실패: {exc}')
            return False
        sleep(self.config.focus_settle_seconds)
        ok = self.runtime.send_text(self.target.input_x, self.target.input_y, self.config.command)
        if ok:
            self.success_count += 1
            self.last_status = f'{self.config.command} 전송 성공'
        else:
            self.failure_count += 1
            self.last_status = f'{self.config.command} 전송 실패'
        self._emit(f'[전송] {self.config.command} 전송 성공' if ok else f'[전송] {self.config.command} 전송 실패')
        if ok and self.config.max_success_count is not None and self.success_count >= self.config.max_success_count:
            self.shutdown_requested = True
            self.running = False
            self._stop_event.set()
            self.last_status = f'목표 {self.config.max_success_count}회 완료'
            self._emit(f'[완료] 목표 {self.config.max_success_count}회 도달')
        return ok

    def start_loop(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return
        self.running = True
        self._stop_event.clear()
        self._thread = Thread(target=self._run_loop, name='simple-repeat-macro', daemon=True)
        self._thread.start()
        self._emit('[F10] 반복 전송을 시작합니다.')

    def stop_loop(self) -> None:
        self.running = False
        self._stop_event.set()
        self._emit('[F12] 정지했습니다.')

    def request_shutdown(self) -> None:
        self.shutdown_requested = True
        self.stop_loop()
        self.last_status = '종료 요청 수신'
        self._emit('[종료] 단순 반복 프로그램을 종료합니다.')

    def summary_text(self) -> str:
        if self.target is None:
            target_text = '대상 없음'
        else:
            target_text = (
                f'{self.target.window_title} / HWND={self.target.window_handle} / '
                f'({self.target.input_x}, {self.target.input_y})'
            )
        return (
            f'최종 요약: 시도 {self.attempt_count}회 / 성공 {self.success_count}회 / 실패 {self.failure_count}회 / '
            f'대상 {target_text} / 마지막 상태 {self.last_status}'
        )

    def _run_loop(self) -> None:
        while not self._stop_event.is_set():
            if self.running:
                self.send_once()
            sleep(self.config.delay_seconds)


def handle_f9_press(controller: SimpleRepeatController, *, capture_target, notify) -> object | None:
    if controller.running or (controller._thread is not None and controller._thread.is_alive()):
        controller.stop_loop()
        notify('[F9] 정지했습니다.')
        return None
    return capture_target()


def handle_f10_press(controller: SimpleRepeatController, *, notify) -> None:
    if controller.target is None:
        notify('먼저 F9로 대상 창을 지정하세요.')
        return
    if controller._thread is None or not controller._thread.is_alive():
        controller.start_loop()
        return
    controller.running = not controller.running
    notify('다시 시작합니다.' if controller.running else '일시정지')


def missing_simple_repeat_dependencies(*, on_windows: bool | None = None) -> list[str]:
    if on_windows is None:
        import os

        on_windows = os.name == 'nt'
    if not on_windows:
        return []

    required = ('pyautogui', 'keyboard', 'win32gui')
    return [name for name in required if importlib.util.find_spec(name) is None]


# 실행 진입점

def capture_foreground_target() -> RepeatTarget:
    import pyautogui  # type: ignore
    import win32gui  # type: ignore

    handle = int(win32gui.GetForegroundWindow())
    title = str(win32gui.GetWindowText(handle)).strip() or '알 수 없는 창'
    x, y = pyautogui.position()
    return RepeatTarget(window_handle=handle, window_title=title, input_x=int(x), input_y=int(y))


def prompt_repeat_limit(*, input_fn=input, notify=append_log) -> int | None:
    while True:
        raw = input_fn('반복 횟수 입력 (0 또는 빈값 = 무한 반복): ').strip()
        if raw in {'', '0'}:
            return None
        try:
            value = int(raw)
        except ValueError:
            notify('반복 횟수는 0 이상 정수로 입력하세요.')
            continue
        if value < 0:
            notify('반복 횟수는 0 이상 정수로 입력하세요.')
            continue
        return value


def finalize_run(controller: SimpleRepeatController) -> int:
    summary = controller.summary_text()
    append_log(summary)
    write_summary(summary)
    return 0


def emit_session_banner(*, repeat_limit: int | None) -> None:
    append_log('=== 낚시 단순반복 ===')
    append_log('F9  : 대상 창 + 입력 위치 지정')
    append_log('F10 : 시작 / 일시정지 / 재개')
    append_log('F12 : 정지')
    append_log('반복 횟수: 무한 반복' if repeat_limit is None else f'반복 횟수: {repeat_limit}회')
    append_log(f'종료 요약 파일: {SUMMARY_PATH}')
    append_log('종료하려면 Ctrl+C')


def run_program() -> int:
    missing = missing_simple_repeat_dependencies()
    if missing:
        message = f"필수 모듈이 없습니다: {', '.join(missing)}"
        print(message)
        print('먼저 실행: py -m pip install -r requirements.txt')
        append_log(message)
        write_summary(message)
        return 1

    import keyboard  # type: ignore

    repeat_limit = prompt_repeat_limit()
    controller = SimpleRepeatController(
        runtime=SimpleRepeatRuntime(event_sink=append_log),
        config=RepeatConfig(max_success_count=repeat_limit),
        event_sink=append_log,
    )

    def capture_target():
        append_log('3초 안에 카카오톡 입력창 위에 마우스를 올리고 창을 클릭하세요...')
        time.sleep(3)
        target = capture_foreground_target()
        controller.set_target(target)
        return target

    keyboard.add_hotkey('f9', lambda: handle_f9_press(controller, capture_target=capture_target, notify=append_log))
    keyboard.add_hotkey('f10', lambda: handle_f10_press(controller, notify=append_log))
    keyboard.add_hotkey('f12', controller.request_shutdown)

    emit_session_banner(repeat_limit=repeat_limit)

    try:
        while not controller.shutdown_requested:
            time.sleep(0.2)
    except KeyboardInterrupt:
        controller.request_shutdown()
        return finalize_run(controller)

    return finalize_run(controller)


def main() -> int:
    try:
        return run_program()
    except Exception as exc:
        return report_startup_failure(exc)


_sync_module_globals()

if __name__ == '__main__':
    raise SystemExit(main())
