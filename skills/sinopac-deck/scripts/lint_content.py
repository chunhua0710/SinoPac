#!/usr/bin/env python3
"""content.md 機械檢查：字數上限、標題長度、禁詞裸用提示。用法：python3 lint_content.py content.md"""
import re, sys, unicodedata

def w(s):  # 全形字計 1、半形計 0.5
    s = re.sub(r'\*\*|__|`', '', s)
    return sum(1 if unicodedata.east_asian_width(c) in 'WF' else .5 for c in s)

LIM = {'title': (12, 22), 'kicker': (0, 10), 'li': (10, 22), 'note': (0, 16),
       'detail': (0, 26), 'quote': (0, 24), 'dx': (0, 24)}
BAN = re.compile(r'賦能|打造|助力|深化|致力|攜手|全面提升|顯著|大幅|積極(布局|推動)|持續(精進|優化)')

page, errs = '?', 0
for n, line in enumerate(open(sys.argv[1], encoding='utf-8'), 1):
    line = line.rstrip()
    if line.startswith('## '):
        page = line[3:].split('｜')[0]; continue
    m = re.match(r'^([\w.]+):\s*(.+)$', line) or re.match(r'^- (.+)$', line)
    if not m: continue
    key, txt = (m.groups() if m.lastindex == 2 else ('li', m.group(1)))
    key = key.split('.')[-1]
    if key in LIM:
        lo, hi = LIM[key]; L = w(txt)
        if not lo <= L <= hi:
            print(f'[{page}] L{n} {key} 字數 {L:.0f}（限 {lo}–{hi}）：{txt[:30]}'); errs += 1
    if BAN.search(txt):
        print(f'[{page}] L{n} 禁詞命中（確認是否裸用）：{txt[:30]}')
print(f'\n{"未通過，" if errs else "字數全數通過，"}共 {errs} 項超標。禁詞命中請人工逐一判斷。')
sys.exit(1 if errs else 0)
