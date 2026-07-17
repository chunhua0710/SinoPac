#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""content.md 機械檢查 v2（配合 build_deck.py 的頁面格式）
檢查：元素字數帶、行數預算、頁面密度（過疏/過密）、同清單行數一致、
結論列（缺漏/複述標題/超長）、禁詞、中國用語。
用法：python3 lint_content.py content.md
規格來源：references/writing.md §二（字/行 × 行數）與 §二之二（行數預算）。
"""
import math, re, sys, unicodedata
from collections import defaultdict

SEP = '｜'

def w(s):  # 全形計 1、半形計 0.5
    return sum(1 if unicodedata.east_asian_width(c) in 'WF' else .5 for c in s)

_MARK = [
    (re.compile(r'\*\*(.+?)\*\*'), r'\1'),
    (re.compile(r'\[(?:k|kb|mark|mute|hl)\](.+?)\[/(?:k|kb|mark|mute|hl)\]'), r'\1'),
    (re.compile(r'\[tip=[^\]]+\](.+?)\[/tip\]'), r'\1'),
    (re.compile(r'\[br\]'), ''),
]
def plain(s):
    for p, r in _MARK:
        s = p.sub(r, s)
    return s.strip()

def lines_of(txt, cpl):
    """估行數：字數 / 每行字數；無 cpl 視為 1 行"""
    if not cpl:
        return 1
    return max(1, math.ceil(w(txt) / cpl))

# (pattern, key) -> [(欄位index|None=整行|'*'=每欄, 名稱, min字, max字, 字/行, 行上限)]
SPEC = {
    ('cover', 'ct'):      [(None, '主標', 0, 18, None, 1)],
    ('cover', 'who'):     [(None, '報告人', 0, 14, None, 1)],
    ('agenda', 'item'):   [(0, '項目名', 0, 8, None, 1), (1, '預告', 0, 12, None, 1)],
    ('divider', 'dt'):    [(None, '章名', 0, 8, None, 1)],
    ('divider', 'dx'):    [(None, '引言', 0, 24, None, 1)],
    ('compare', 'a.li'):  [(1, '條列', 10, 48, 26, 2)],
    ('compare', 'b.li'):  [(1, '條列', 10, 48, 26, 2)],
    ('cards', 'card'):    [(0, '卡名', 0, 4, None, 1), (2, '箭頭句', 0, 12, None, 1),
                           (3, '卡說明', 28, 70, 14, 5)],
    ('kpi', 'kpi'):       [(2, 'KPI標籤', 0, 8, None, 1), (3, 'KPI說明', 0, 42, 14, 3)],
    ('table', 'th'):      [('*', '表頭', 0, 6, None, 1)],
    ('table', 'row'):     [('*', '儲存格', 0, 12, None, 1)],
    ('matrix', 'q'):      [(1, '象限標', 0, 8, None, 1), (2, '象限說明', 0, 64, 32, 2)],
    ('case', 'bg'):       [(None, '背景', 0, 52, 26, 2)],
    ('case', 'how'):      [(None, '做法', 0, 52, 26, 2)],
    ('case', 'out'):      [(None, '產出', 0, 20, None, 1)],
    ('case', 'why'):      [(None, '效益', 0, 40, None, 2)],
    ('timeline', 'step'): [(1, '步名', 0, 6, None, 1), (2, '步說明', 0, 45, 15, 3)],
    ('optiontabs', 'tab.body'): [(None, '方案主文', 40, 136, 34, 4)],
    ('optiontabs', 'tab.pro'):  [('*', '優勢條', 0, 12, None, 1)],
    ('optiontabs', 'tab.con'):  [('*', '取捨條', 0, 12, None, 1)],
    ('ask', 'item'):      [(0, '事項標題', 6, 14, None, 1), (1, '依據', 0, 40, 41, 1)],
    ('ask', 'fact'):      [(0, 'fact值', 0, 6, None, 1), (2, 'fact說明', 0, 20, None, 1)],
    ('prose', 'p'):       [(None, '段落', 0, 68, 34, 2)],
    ('quote', 'q'):       [(None, '金句', 0, 36, None, 3)],
    ('quote', 'by'):      [(None, '署名', 0, 12, None, 1)],
    ('closing', 'q'):     [(None, '金句', 0, 24, None, 2)],
    ('closing', 'sub'):   [(None, '補充', 0, 32, None, 1)],
}
# 每版型密度門檻（估算單位＝lint 累計的行單位；多欄版型並排、門檻較高）
DENSITY = {'compare': (6, 20), 'cards': (9, 24), 'kpi': (6, 16), 'table': (4, 9),
           'matrix': (5, 12), 'case': (5, 12), 'timeline': (5, 14),
           'optiontabs': (6, 16), 'prose': (8, 34), 'ask': (5, 14)}
CONTENT = set(DENSITY)
FUNCTIONAL_TITLE_OK = {'cover', 'agenda', 'divider', 'quote', 'closing', 'blank'}

BAN = re.compile(r'賦能|打造|助力|深化|致力|攜手|全面提升|顯著|大幅|積極(布局|推動)|持續(精進|優化)|有效(提升|改善)')
CN = re.compile(r'視頻|質量|信息|網絡|軟件|硬件|數據庫|服務器|屏幕|鼠標|默認|兼容|反饋|卸載|性價比|顆粒度|復盤|智能')

def main(path):
    errs, warns = [], []
    page = None
    page_lines = defaultdict(int)     # pageno -> 估計內文行數
    list_lines = defaultdict(list)    # (pageno, key) -> [每條行數]
    titles, blufs = {}, {}
    pages = []

    for n, raw in enumerate(open(path, encoding='utf-8'), 1):
        line = raw.rstrip()
        if line.startswith('## '):
            m = re.match(r'^##\s*([^｜|]+)[｜|]\s*(\w[\w-]*)\s*[｜|]\s*(.+?)\s*$', line)
            if not m:
                errs.append(f'L{n} 頁首格式錯誤：{line}')
                page = None; continue
            page = (m.group(1).strip(), m.group(2).strip(), m.group(3).strip(), n)
            pages.append(page); continue
        if not page or not line.strip() or line.lstrip().startswith(('//', '#', '<<<', '>>>')):
            continue
        m = re.match(r'^([\w.\-]+):\s*(.*)$', line)
        if not m:
            continue
        key, val = m.group(1), plain(m.group(2))
        no, pat = page[0], page[1]

        if BAN.search(val):
            warns.append(f'[{no}·{pat}] L{n} 禁詞命中（確認是否裸用）：{val[:28]}')
        if CN.search(val):
            errs.append(f'[{no}·{pat}] L{n} 中國用語（對外零容忍）：{val[:28]}')

        if key == 'title':
            titles[no] = val
            L = w(val)
            if pat not in FUNCTIONAL_TITLE_OK and not 12 <= L <= 22:
                errs.append(f'[{no}·{pat}] L{n} 標題 {L:.0f} 字（限 12–22）：{val[:28]}')
            continue
        if key == 'kicker':
            if w(val) > 10:
                errs.append(f'[{no}·{pat}] L{n} 眉標 {w(val):.0f} 字（限 ≤10）：{val}')
            continue
        if key == 'bluf':
            parts = [p.strip() for p in val.split(SEP)]
            text = parts[-1]
            blufs[no] = text
            L = w(text)
            if L > 100:
                errs.append(f'[{no}·{pat}] L{n} 結論列 {L:.0f} 字（硬限 3 行 100 字）')
            elif not 24 <= L <= 70:
                warns.append(f'[{no}·{pat}] L{n} 結論列 {L:.0f} 字（建議 24–70）：{text[:28]}')
            page_lines[no] += lines_of(text, 58)
            continue

        spec = SPEC.get((pat, key))
        if not spec:
            continue
        fields = [f.strip() for f in val.split(SEP)]
        is_lead = len(fields) > 5 and 'lead' in fields[5].split()
        page_add = 0
        for idx, name, lo, hi, cpl, maxlines in spec:
            if idx == '*':
                targets = fields
            elif idx is None:
                targets = [val]
            elif isinstance(idx, int) and idx < len(fields):
                targets = [fields[idx]]
            else:
                targets = []
            for t in targets:
                t = re.sub(r'^(ok|run|warn):', '', t)   # 表格 chip 前綴
                if not t:
                    continue
                L = w(t)
                if L > hi:
                    detail = f'，約 {lines_of(t, cpl)} 行 > {maxlines} 行' if cpl and lines_of(t, cpl) > maxlines else ''
                    errs.append(f'[{no}·{pat}] L{n} {name} {L:.0f} 字（限 {lo or 0}–{hi}{detail}）：{t[:24]}')
                elif lo and L < lo:
                    warns.append(f'[{no}·{pat}] L{n} {name}僅 {L:.0f} 字（建議 ≥{lo}——'
                                 f'此欄有 {maxlines} 行預算可用）：{t[:24]}')
                if cpl:
                    ln = lines_of(t, cpl)
                    page_add += ln
                    if not is_lead and (pat, key) != ('prose', 'p'):
                        list_lines[(no, key)].append((ln, w(t)))
                elif idx != '*':
                    page_add += 1
        page_lines[no] += page_add or 1

    for no, pat, label, ln in pages:
        if pat not in CONTENT:
            continue
        total = page_lines[no]
        lo, hi = DENSITY[pat]
        if total and total < lo:
            warns.append(f'[{no}·{pat}] 內文估僅 {total} 行單位＝過疏（門檻 {lo}）——'
                         f'補第二資訊點、放大焦點或併頁（writing.md §二之二）')
        elif total > hi:
            warns.append(f'[{no}·{pat}] 內文估 {total} 行單位＝過密（門檻 {hi}）——'
                         f'拆頁、改 prose 或 scroll: 1')
        if no in titles and no not in blufs and pat != 'blank':
            warns.append(f'[{no}·{pat}] 缺結論列 bluf（內容頁固定配備，writing.md §〇）')
        if no in blufs and no in titles:
            t, b = titles[no], blufs[no]
            grams = {t[i:i+2] for i in range(len(t) - 1)} - {'：', '，'}
            if grams:
                hit = sum(1 for g in grams if g in b) / len(grams)
                if hit >= .7:
                    warns.append(f'[{no}] 結論列疑似複述標題（重合 {hit:.0%}）——'
                                 f'改寫成後果＋行動（writing.md §〇）')
    for (no, key), pairs in list_lines.items():
        lns = [p[0] for p in pairs]; chars = [p[1] for p in pairs]
        if len(lns) >= 3 and len(set(lns)) > 1 and max(chars) - min(chars) > 8:
            warns.append(f'[{no}] {key} 清單行數不一（{lns}）——同清單全 1 行或全 2 行'
                         f'（長度差 {max(chars)-min(chars):.0f} 字 > 8）')

    for e in errs:
        print('✗', e)
    for x in warns:
        print('△', x)
    print(f'\n{len(errs)} 項超標（✗ 必改）、{len(warns)} 則警告（△ 人工判斷）。')
    return 1 if errs else 0

if __name__ == '__main__':
    if len(sys.argv) != 2:
        print(__doc__); sys.exit(2)
    sys.exit(main(sys.argv[1]))
