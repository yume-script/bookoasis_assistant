"""같은 모듈 안 함수를 없는 키워드 인자로 부르는 곳이 없는지 (함수 인자를 바꾸고 호출부를 빠뜨린 경우).

예: 2.65 때 kakao_pipeline.ready_at()에서 nums 인자를 뺐는데 작품 처리의 호출 하나가 nums=를 그대로 넘겨
카카오 작품마다 'unexpected keyword argument' 오류로 하루 동안 아무것도 받지 못했다."""
import ast
import glob
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _bad_calls(path):
    tree = ast.parse(open(path, encoding="utf-8").read())
    defs = {}
    for n in tree.body:
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and not n.args.kwarg:
            a = n.args
            defs[n.name] = {x.arg for x in a.posonlyargs + a.args + a.kwonlyargs}
    out = []
    for n in ast.walk(tree):
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id in defs:
            bad = {k.arg for k in n.keywords if k.arg} - defs[n.func.id]
            if bad:
                out.append("%s:%d %s(%s)" % (os.path.relpath(path, ROOT), n.lineno, n.func.id, ", ".join(sorted(bad))))
    return out


def test_module_local_calls_use_known_keywords():
    bad = []
    for d in ("wtm", "gdw", "tgup", "brunch"):
        for path in sorted(glob.glob(os.path.join(ROOT, d, "*.py"))):
            bad += _bad_calls(path)
    assert not bad, "없는 키워드 인자로 부르는 곳: " + "; ".join(bad)


def test_kakao_ready_at_callers():
    """다른 모듈에서 kp.ready_at(...)으로 부르는 곳도"""
    import inspect
    from wtm import kakao_pipeline as kp
    allowed = set(inspect.signature(kp.ready_at).parameters)
    bad = []
    for path in glob.glob(os.path.join(ROOT, "wtm", "*.py")):
        for n in ast.walk(ast.parse(open(path, encoding="utf-8").read())):
            if isinstance(n, ast.Call) and getattr(n.func, "attr", getattr(n.func, "id", "")) == "ready_at":
                extra = {k.arg for k in n.keywords if k.arg} - allowed
                if extra:
                    bad.append("%s:%d %s" % (os.path.basename(path), n.lineno, extra))
    assert not bad, bad


def test_hidden_menus(monkeypatch):
    from gdw import web
    monkeypatch.delenv("MENU_HIDDEN", raising=False)
    assert web.hidden_menus() == ["brunch"]
    monkeypatch.setenv("MENU_HIDDEN", "")
    assert web.hidden_menus() == []
    monkeypatch.setenv("MENU_HIDDEN", "brunch, mini")
    assert web.hidden_menus() == ["brunch", "mini"]
