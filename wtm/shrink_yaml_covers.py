# -*- coding: utf-8 -*-
"""이미 만들어진 kavita.yaml의 표지를 한 번에 줄인다 (표지 한 줄만 바꾸고 나머지는 그대로).

    python3 -m wtm.shrink_yaml_covers              미리 보기 (줄일 파일 수와 줄어드는 크기만)
    python3 -m wtm.shrink_yaml_covers --apply      적용
    python3 -m wtm.shrink_yaml_covers --apply 200  가로 200px로 (기본: 설정 KAVITA_YAML_COVER_WIDTH, 300)

네이버·카카오웹툰·카카오웹소설 저장 경로의 작품 폴더마다 kavita.yaml을 찾아, 첫 표지(base64)를 가로 N px JPEG로
바꿔 쓴다. 이미 작은 표지는 건드리지 않는다. 새로 만들거나 갱신되는 yaml은 이 도구 없이도 줄어든 표지로 써진다.
서비스를 멈추지 않아도 된다 (파일을 통째로 바꿔 넣으므로 읽는 쪽이 반쯤 쓴 파일을 보지 않음).
Pillow가 필요하다: venv/bin/pip install Pillow
"""
import json
import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from gdw import config  # noqa: E402

config.load_env()
config.utf8_console()
os.environ.setdefault("WTM_HOST", "1")


def _roots(cfg):
    from wtm import kakao_pipeline as kp, state_store as ss
    roots = [cfg.get("DOWNLOAD_ROOT") or ss.DOWNLOAD_DEFAULT_DIR, kp.kakao_root(cfg), kp.kakao_novel_root(cfg)]
    out = []
    for r in roots:
        r = os.path.normpath(str(r or ""))
        if r and r not in out and os.path.isdir(r):
            out.append(r)
    return out


def shrink_file(path, width, apply):
    """반환 (전 크기, 후 크기) - 바꿀 게 없으면 None"""
    from wtm import kavita_yaml as ky
    with open(path, encoding="utf-8") as f:
        text = f.read()
    lines = text.split("\n")
    for i, line in enumerate(lines):
        s = line.strip()
        if not s.startswith("cover:"):
            continue
        raw = s[len("cover:"):].strip()
        val = json.loads(raw) if raw.startswith('"') else raw
        if val in ("", "FIRST", "''"):
            return None
        small = ky.shrink_cover(val, width=width)
        if small == val:
            return None
        indent = line[:len(line) - len(line.lstrip())]
        lines[i] = indent + "cover: " + (json.dumps(small) if raw.startswith('"') else small)
        new = "\n".join(lines)
        if apply:
            tmp = path + ".tmp"
            with open(tmp, "w", encoding="utf-8", newline="\n") as f:
                f.write(new)
            from wtm import state_store as ss
            ss.replace_file(tmp, path)
        return len(text.encode("utf-8")), len(new.encode("utf-8"))
    return None


def main(argv):
    from wtm import host, kavita_yaml as ky
    apply = "--apply" in argv
    nums = [a for a in argv if a.isdigit()]
    width = int(nums[0]) if nums else (ky.cover_width() or 300)
    try:
        import PIL  # noqa: F401
    except ImportError:
        print("Pillow가 없습니다: venv/bin/pip install Pillow")
        return 1
    cfg = host.load_settings()
    roots = _roots(cfg)
    print("■ kavita.yaml 표지를 가로 %dpx JPEG로 %s (경로: %s)" % (width, "줄입니다" if apply else "줄이면 (미리 보기)",
                                                           ", ".join(roots) or "없음"))
    files = changed = 0
    before = after = 0
    t0 = time.time()
    for root in roots:
        for name in sorted(os.listdir(root)):
            path = os.path.join(root, name, ky.YAML_NAME)
            if not os.path.isfile(path):
                continue
            files += 1
            try:
                r = shrink_file(path, width, apply)
            except Exception as e:  # noqa: BLE001
                print("  건너뜀 %s: %s" % (name, e))
                continue
            if r:
                changed += 1
                before += r[0]
                after += r[1]
            if files % 200 == 0:
                print("  … %d개 확인, %d개 %s (%.0f초)" % (files, changed, "줄임" if apply else "줄일 대상", time.time() - t0))
    print("\nyaml %d개 중 %d개 %s: %.1fMB → %.1fMB" % (files, changed, "줄임" if apply else "줄일 수 있음",
                                                   before / 1048576, after / 1048576))
    if not apply:
        print("적용하려면: python3 -m wtm.shrink_yaml_covers --apply")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
