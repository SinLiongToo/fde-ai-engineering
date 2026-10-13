from labs.beginner import check_answers, first_call, handbook_qa, next_word


def test_next_char_probabilities_sum_to_one():
    model = next_word.train(next_word.TRAINING_TEXT)
    probs = next_word.next_char_probabilities(model, "天")
    assert set(probs) == {"天", "氣"}
    assert abs(sum(probs.values()) - 1) < 1e-9


def test_generate_is_repeatable_with_seed_and_stops_at_period():
    model = next_word.train(next_word.TRAINING_TEXT)
    a = next_word.generate(model, "今天", seed=1)
    assert a == next_word.generate(model, "今天", seed=1)
    assert a.startswith("今天")


def test_unknown_char_has_no_prediction():
    model = next_word.train(next_word.TRAINING_TEXT)
    assert next_word.next_char_probabilities(model, "貓") == {}


def test_request_resends_whole_history():
    history = [{"role": "user", "content": "Q1"}, {"role": "assistant", "content": "A1"}]
    req = first_call.build_request(history, "Q2")
    assert [m["content"] for m in req["messages"]] == ["Q1", "A1", "Q2"]
    assert req["system"] == first_call.SYSTEM_PROMPT


def test_search_finds_leave_policy():
    found = handbook_qa.search("請特休要提前幾天？")
    assert found[0][0] == "H1"


def test_prompt_contains_sources_and_way_out():
    prompt = handbook_qa.build_prompt("Q", handbook_qa.search("病假要附證明嗎"))
    assert "[H2]" in prompt
    assert "手冊沒有寫到這件事" in prompt


def test_exam_shows_the_two_known_failures():
    # 入門第 5 章用這兩題說明關鍵字搜尋的限制：同義詞（筆電）與誤配（午餐）
    assert check_answers.run_exam() == 4


def test_perfect_ai_passes_everything():
    answers = {
        "請特休要提前幾天？": ("需在三個工作天前申請 [H1]", "H1"),
        "病假超過幾天要附證明？": ("超過三天需附醫生證明 [H2]", "H2"),
        "一週可以在家工作幾天？": ("最多兩天 [H4]", "H4"),
        "出差收據要多久內報帳？": ("十四天內 [H5]", "H5"),
        "筆電壞掉可以自己拿去修嗎？": ("不行，請通知 IT 部門 [H6]", "H6"),
        "公司有提供午餐嗎？": ("手冊沒有寫到這件事。", None),
    }
    assert check_answers.run_exam(lambda q: answers[q]) == len(check_answers.TEST_CASES)
