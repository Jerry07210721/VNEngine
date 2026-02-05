from src.game.var_expr import eval_var_expr


def test_eval_var_expr_basic_compare_and_bool_ops():
    vars_ = {"love": 12, "flag": 1, "name": "Alice"}
    assert eval_var_expr("love >= 10", vars_) is True
    assert eval_var_expr("love < 10", vars_) is False
    assert eval_var_expr("flag == 1 and love >= 10", vars_) is True
    assert eval_var_expr("flag == 0 or love >= 10", vars_) is True
    assert eval_var_expr("name == 'Alice'", vars_) is True


def test_eval_var_expr_empty_or_invalid_returns_false():
    assert eval_var_expr("", {"x": 1}) is False
    assert eval_var_expr(None, {"x": 1}) is False
    assert eval_var_expr("(", {"x": 1}) is False


def test_eval_var_expr_disallows_calls_and_attributes():
    # must not allow arbitrary code execution
    assert eval_var_expr("__import__('os').system('echo hi')", {"x": 1}) is False
    assert eval_var_expr("(1).__class__", {"x": 1}) is False
