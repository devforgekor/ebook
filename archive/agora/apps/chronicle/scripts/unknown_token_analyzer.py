"""
unknown_token_analyzer.py

- 지정된 vocab 파일과 데이터셋(jsonl) 파일을 입력받아,
- messages 배열 내 모든 텍스트를 vocab 기준으로 토큰화
- vocab에 없는 토큰(unknown) 빈도/예시를 통계로 출력
- 결과: unknown 토큰별 count, 예시, 전체 토큰 대비 unknown 비율 등

사용법 예시:
python unknown_token_analyzer.py --vocab vocab.txt --input chat_ko_review_2026-03-15.jsonl

vocab.txt: 줄마다 1개 토큰(단어)
"""
import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path
import re

def load_vocab(vocab_path):
    vocab = set()
    with open(vocab_path, encoding="utf-8") as f:
        for line in f:
            token = line.strip()
            if token:
                vocab.add(token)
    return vocab

def tokenize(text):
    # 기본: 공백/특수문자 기준 단어 분리 (한글+영어+숫자)
    return re.findall(r"[\w가-힣]+", text)

def analyze_unknown(input_path, vocab):
    unknown_counter = Counter()
    unknown_examples = defaultdict(list)
    total_tokens = 0
    with open(input_path, encoding="utf-8") as f:
        for line in f:
            obj = json.loads(line)
            for msg in obj.get("messages", []):
                tokens = tokenize(msg.get("content", ""))
                total_tokens += len(tokens)
                for t in tokens:
                    if t not in vocab:
                        unknown_counter[t] += 1
                        if len(unknown_examples[t]) < 3:
                            unknown_examples[t].append(msg.get("content", ""))
    return unknown_counter, unknown_examples, total_tokens

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--vocab", required=True, help="vocab.txt (줄마다 1토큰)")
    parser.add_argument("--input", required=True, help="분석할 jsonl 파일")
    parser.add_argument("--topk", type=int, default=30, help="상위 N개 unknown만 출력")
    args = parser.parse_args()

    vocab = load_vocab(args.vocab)
    unknown_counter, unknown_examples, total_tokens = analyze_unknown(args.input, vocab)

    print(f"총 토큰 수: {total_tokens}")
    print(f"unknown 토큰 종류: {len(unknown_counter)}개, 전체 토큰 대비 비율: {sum(unknown_counter.values())/total_tokens:.2%}")
    print(f"상위 {args.topk}개 unknown 토큰:")
    for token, count in unknown_counter.most_common(args.topk):
        print(f"{token}: {count}회, 예시: {unknown_examples[token][0]}")

if __name__ == "__main__":
    main()
