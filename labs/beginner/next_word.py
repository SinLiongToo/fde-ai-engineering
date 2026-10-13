"""
入門 1：一個超迷你的「猜下一個字」模型

真正的大型語言模型 (LLM) 用的是神經網路、讀過大量文字。
這個檔案只用「數數看哪個字最常跟在哪個字後面」，但核心想法是一樣的：
    看前面的文字 → 猜下一個字 → 接上去 → 再猜下一個字

執行：python -m labs.beginner.next_word
"""

import random
from collections import Counter, defaultdict

# 訓練資料：模型只「讀過」這幾句話
TRAINING_TEXT = [
    "今天天氣很好，我們去公園散步。",
    "今天天氣很冷，我們在家喝咖啡。",
    "明天天氣很熱，我們去海邊游泳。",
    "我們在公園喝咖啡。",
    "我們去海邊散步。",
    "咖啡很好喝。",
]


def train(sentences):
    """數一數：每個字後面，出現過哪些字、各幾次。"""
    counts = defaultdict(Counter)
    for sentence in sentences:
        for current_char, next_char in zip(sentence, sentence[1:]):
            counts[current_char][next_char] += 1
    return counts


def next_char_probabilities(counts, text):
    """看最後一個字，算出下一個字的機率。"""
    last_char = text[-1]
    followers = counts.get(last_char)
    if not followers:
        return {}
    total = sum(followers.values())
    return {char: n / total for char, n in followers.most_common()}


def generate(counts, start, max_chars=20, seed=None):
    """從 start 開始，一次猜一個字，直到句號或達到長度上限。"""
    rng = random.Random(seed)
    text = start
    for _ in range(max_chars):
        probs = next_char_probabilities(counts, text)
        if not probs:
            break
        # 依機率抽一個字：機率高的比較常被選到，但不是每次都一樣
        chars = list(probs)
        weights = list(probs.values())
        text += rng.choices(chars, weights=weights)[0]
        if text.endswith("。"):
            break
    return text


if __name__ == "__main__":
    model = train(TRAINING_TEXT)

    print("「天」後面可能接什麼？")
    for char, p in next_char_probabilities(model, "天").items():
        print(f"  {char}  {p:.0%}")

    print("\n從「今天」開始，生成 5 次（每次可能不同）：")
    for i in range(5):
        print(" ", generate(model, "今天", seed=i))

    print("\n注意：它可能寫出「今天天氣很熱，我們在家喝咖啡。」這種訓練資料裡沒有的句子。")
    print("通順，但不一定是事實。這就是大型語言模型會「一本正經地說錯話」的原因之一。")
