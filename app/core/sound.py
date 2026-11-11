"""音效播放：WAV 用 winsound，MP3 用 miniaudio 后台线程播放。

音效文件取自 dsh-whale-widget-plus（默认「小黄鸭」音效组）：
Ya1.mp3 = 按下，Ya2.mp3 = 松开，均为 GitHub 原文件、未做二次修改。
"""
from __future__ import annotations

import sys
import threading
import time
from pathlib import Path


def play_wav(path: str | Path) -> bool:
    """Windows 下用 winsound 异步播放 WAV。"""
    if sys.platform != "win32":
        return False
    sound = Path(path)
    if not sound.exists():
        return False
    try:
        import winsound

        winsound.PlaySound(
            str(sound),
            winsound.SND_FILENAME | winsound.SND_ASYNC | winsound.SND_NODEFAULT,
        )
        return True
    except Exception:
        return False


def play_sound(path: str | Path) -> bool:
    """按扩展名播放音效；MP3 原样解码，不做转码或改音。"""
    sound = Path(path)
    if not sound.exists():
        return False
    if sound.suffix.lower() == ".wav":
        return play_wav(sound)
    try:
        import miniaudio  # noqa: F401  确认解码库可用再起线程
    except Exception:
        return False
    threading.Thread(target=_play_mp3, args=(sound,), daemon=True).start()
    return True


def _play_mp3(sound: Path) -> None:
    """用 miniaudio 独立播放一次；短音效播完即关闭设备。"""
    try:
        import miniaudio

        info = miniaudio.get_file_info(str(sound))
        device = miniaudio.PlaybackDevice()
        stream = miniaudio.stream_file(
            str(sound),
            nchannels=info.nchannels,
            sample_rate=info.sample_rate,
        )
        device.start(stream)
        time.sleep(float(info.duration) + 0.12)
        device.close()
    except Exception:
        pass
