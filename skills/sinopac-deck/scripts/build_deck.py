#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""sinopac-deck 組裝器（S2 機械步驟，零模型 token）

用法：
  python3 build_deck.py content.md -o deck.html          # 組裝
  python3 build_deck.py --list                           # 列出全部版型
  python3 build_deck.py --schema compare                 # 查單一版型的槽位格式
  python3 build_deck.py content.md --check               # 只驗證不輸出

content.md 格式（欄位分隔一律用全形「｜」）：
  # meta
  title: 檔案標題（瀏覽器分頁名）

  ## 01｜cover｜封面
  ct: 主標題
  who: ○○部門　報告人
  date: 2026 / 07

  ## 02｜compare｜對照
  kicker: 01 · 現況對照
  title: 頁標題（判斷句）
  bluf: 結論文字（或「請示｜文字」自訂前置章；請示/行動/決議轉紅）
  a: BEFORE｜現行做法｜人工作業
  a.li: ×｜條列文字
  b: AFTER｜導入後｜自動化流程
  b.li: ✓｜**關鍵字**——條列文字

  # custom-css        ←（選用）自訂樣式，注入 style#deck-custom
  <<<
  .my-rule{...}
  >>>

行內標記（先跳脫 HTML 再轉換，內文不得手寫 HTML；blank 版型的 html 圍欄除外）：
  **粗體**  [k]紅關鍵字[/k]  [kb]藍關鍵字[/kb]  [mark]淡底強調[/mark]
  [mute]弱化[/mute]  [hl]封底金句強調[/hl]  [br]換行
  [tip=白話解釋]名詞[/tip] → hover 提示
"""
import argparse, html as _html, re, sys, unicodedata
from pathlib import Path

SEP = '｜'
HERE = Path(__file__).resolve().parent
TEMPLATE = HERE.parent / 'assets' / 'template.html'

# ─────────────────────────── 行內標記 ───────────────────────────

def esc(s: str) -> str:
    return _html.escape(s, quote=False)

_INLINE = [
    (re.compile(r'\*\*(.+?)\*\*'), r'<b>\1</b>'),
    (re.compile(r'\[k\](.+?)\[/k\]'), r'<span class="k">\1</span>'),
    (re.compile(r'\[kb\](.+?)\[/kb\]'), r'<span class="kb">\1</span>'),
    (re.compile(r'\[mark\](.+?)\[/mark\]'), r'<span class="mark">\1</span>'),
    (re.compile(r'\[mute\](.+?)\[/mute\]'), r'<span class="mute">\1</span>'),
    (re.compile(r'\[hl\](.+?)\[/hl\]'), r'<span class="hl">\1</span>'),
    (re.compile(r'\[tip=([^\]]+)\](.+?)\[/tip\]'),
     r'<span class="tip" tabindex="0" data-tip="\1">\2</span>'),
    (re.compile(r'\[br\]'), '<br>'),
]

def fmt(s: str) -> str:
    s = esc(s.strip())
    for pat, repl in _INLINE:
        s = pat.sub(repl, s)
    return s

# ─────────────────────────── 解析 ───────────────────────────

class Page:
    def __init__(self, no, pattern, label, line):
        self.no, self.pattern, self.label, self.line = no, pattern, label, line
        self.slots = {}          # key -> [values]（保序）
        self.raw = {}            # key -> 圍欄原文

    def get(self, key, default=None):
        v = self.slots.get(key)
        return v[0] if v else default

    def all(self, key):
        return self.slots.get(key, [])

def parse(path):
    meta, pages, custom_css = {}, [], ''
    cur, section = None, None
    lines = Path(path).read_text(encoding='utf-8').splitlines()
    i = 0
    while i < len(lines):
        line = lines[i]
        if line.startswith('## '):
            m = re.match(r'^##\s*([^｜|]+)[｜|]\s*(\w[\w-]*)\s*[｜|]\s*(.+?)\s*$', line)
            if not m:
                die(f'第 {i+1} 行：頁首格式應為「## 頁碼｜版型｜data-label」：{line}')
            cur = Page(m.group(1).strip(), m.group(2).strip(), m.group(3).strip(), i + 1)
            pages.append(cur); section = 'page'; i += 1; continue
        if line.startswith('# '):
            name = line[2:].strip().lower()
            section = {'meta': 'meta', 'custom-css': 'css'}.get(name)
            if section is None:
                die(f'第 {i+1} 行：未知區段「{line}」（可用：# meta、# custom-css）')
            cur = None; i += 1; continue
        if not line.strip() or line.lstrip().startswith('//'):
            i += 1; continue
        if section == 'css':
            if line.strip() == '<<<':
                j = i + 1
                while j < len(lines) and lines[j].strip() != '>>>':
                    j += 1
                custom_css = '\n'.join(lines[i+1:j]); i = j + 1; continue
            i += 1; continue
        m = re.match(r'^([\w.\-]+):\s*(.*)$', line)
        if not m:
            die(f'第 {i+1} 行：不是「key: value」槽位：{line}')
        key, val = m.group(1), m.group(2)
        if section == 'meta':
            meta[key] = val.strip(); i += 1; continue
        if cur is None:
            die(f'第 {i+1} 行：槽位出現在任何頁面之前：{line}')
        if val.strip() == '' and i + 1 < len(lines) and lines[i+1].strip() == '<<<':
            j = i + 2
            while j < len(lines) and lines[j].strip() != '>>>':
                j += 1
            cur.raw[key] = '\n'.join(lines[i+2:j]); i = j + 1; continue
        cur.slots.setdefault(key, []).append(val.strip())
        i += 1
    return meta, pages, custom_css

def die(msg):
    print(f'[build_deck] 錯誤：{msg}', file=sys.stderr); sys.exit(1)

WARNINGS = []
def warn(msg):
    WARNINGS.append(msg); print(f'[build_deck] 警告：{msg}', file=sys.stderr)

def split(val, n=None, key=''):
    parts = [p.strip() for p in val.split(SEP)]
    if n and len(parts) < n:
        parts += [''] * (n - len(parts))
    return parts

# ─────────────────────────── 版型 ───────────────────────────
# schema: key -> (必填?, 可重複?, 說明)。content 版型自動附掛 kicker/title/bluf/scroll。

COMMON = {
    'kicker': (False, False, '章節眉標「NN · 章名」（≤10 字；可省略）'),
    'title':  (True,  False, '頁標題＝判斷句/行動句（12–22 字）'),
    'bluf':   (False, False, '結論列（建議必填）：「文字」或「前置章｜文字」；請示/行動/決議自動轉紅'),
    'scroll': (False, False, '內容偏密時設 1：.inner 加捲動'),
}

SCHEMAS = {
    'cover': dict(desc='封面：標題＋報告人＋日期', slots={
        'ct':   (True, False, '主標（≤18 字，名詞短語）'),
        'who':  (False, False, '部門／報告人（≤14 字）'),
        'date': (False, False, '日期（如 2026 / 07）')}),
    'agenda': dict(desc='議程：3–8 段目錄', slots={
        'title': (False, False, '預設「今日議程」'),
        'kicker': (False, False, '預設「Agenda」'),
        'item': (True, True, '項目：「名稱｜一句預告」（名稱 ≤8、預告 ≤12 字）')}),
    'divider': dict(desc='章節隔頁：大號章節數字', slots={
        'num': (True, False, '章節號（01、02…）'),
        'dt':  (True, False, '章名（≤8 字）'),
        'dx':  (False, False, '本章要回答的問題（≤24 字）')}),
    'compare': dict(common=True, desc='雙欄對照：藍＝現況、紅＝行動', slots={
        'a':    (True, False, '左欄（藍）：「chip｜面板名｜副註」如 BEFORE｜現行做法｜人工作業'),
        'a.li': (True, True, '左欄條列：「符號｜文字」符號可 × ✓ ○ 等；每側 3–5 條'),
        'b':    (True, False, '右欄（紅）：「chip｜面板名｜副註」'),
        'b.li': (True, True, '右欄條列：「符號｜**關鍵字**——文字」')}),
    'cards': dict(common=True, desc='卡片陣列 3–4 張（lead 卡放第一格可做主從）', slots={
        'card': (True, True, '「卡名｜眉標EN｜箭頭句｜說明｜狀態chip｜flags」flags 可 blue、lead；後兩欄可留空')}),
    'kpi': dict(common=True, desc='數字頁 3–4 格（lead 格放第一格可做主從）', slots={
        'kpi': (True, True, '「值｜單位｜標籤｜說明｜趨勢｜flags」趨勢=「up 文字」或「dn 文字」；flags 可 blue、lead')}),
    'table': dict(common=True, desc='表格 ≤7 列：藍表頭＋狀態 chip', slots={
        'th':  (True, False, '表頭：「欄1｜欄2｜…」（各 ≤6 字）'),
        'row': (True, True, '資料列：「儲存格｜…」；儲存格可用 ok:/run:/warn: 前綴轉狀態 chip')}),
    'matrix': dict(common=True, desc='2×2 定位矩陣（恰 4 象限）', slots={
        'y': (True, False, 'Y 軸標（如 影響力　高 → 低）'),
        'x': (True, False, 'X 軸標（如 可行性　低 → 高）'),
        'q': (True, True, '象限×4，序＝左上｜右上｜左下｜右下：「樣式｜象限標｜說明」樣式∈hot/cool/soft/plain')}),
    'case': dict(common=True, desc='案例：背景/做法 → 產出（指令框選用）', slots={
        'bg':  (True, False, '背景／痛點（≤40 字、含一個數字）'),
        'how': (True, False, '做法（≤40 字）'),
        'cmd': (False, False, '操作指令示意（選用；不需展示指令就省略）'),
        'cmd-label': (False, False, '指令框標籤（預設「指令」）'),
        'out': (True, False, '產出一行'),
        'why': (True, False, '效益一句（可 **粗體** 前置）')}),
    'timeline': dict(common=True, desc='流程/時程 3–5 步（now 標當前）', slots={
        'step': (True, True, '「期標｜步名｜說明｜now」第 4 欄填 now 標示當前階段')}),
    'optiontabs': dict(common=True, desc='方案切換（互動）：2–4 個頁籤', slots={
        'tab':      (True, True, '開新頁籤：「縮寫｜方案名｜副題EN」'),
        'tab.body': (True, True, '該頁籤主文（支援行內標記；緊跟所屬 tab）'),
        'tab.pro':  (False, True, '優勢：「條1｜條2」'),
        'tab.con':  (False, True, '取捨：「條1｜條2」'),
        'tab.acc':  (False, True, '收合補充（選用）：「標題｜內文」')}),
    'quote': dict(desc='觀點頁：大引述（節奏停頓）', slots={
        'kicker': (False, False, '預設「核心觀點」'),
        'q':  (True, False, '金句 ≤24 字（可 [k]…[/k] 上色、[br] 斷行）'),
        'by': (False, False, '署名／出處（≤12 字）')}),
    'prose': dict(common=True, desc='文字密集：結論列＋雙欄段落', slots={
        'p': (True, True, '段落：「**關鍵字**——內文」每段 ≤68 字（2 行內）；6–10 段')}),
    'ask': dict(common=True, desc='決議頁：請示事項＋右欄關鍵條件（v4 新增）', slots={
        'item': (True, True, '請示事項 2–4 條：「行動句標題｜依據一句」'),
        'fact': (False, True, '右欄關鍵條件 ≤4 格：「值｜單位｜說明」')}),
    'blank': dict(common=True, desc='空白畫布：title 可省，內容用 html 圍欄自由發揮', slots={
        'title': (False, False, '可留可刪'),
        'html':  (False, False, '圍欄原始 HTML：html: 換行後 <<< … >>>')}),
    'closing': dict(desc='深色封底：收束金句', slots={
        'q':   (True, False, '收束金句 ≤20 字（[hl]…[/hl] 反白強調）'),
        'sub': (False, False, '補充一行：下一步／徵求決議／窗口')}),
}
CONTENT_PATTERNS = {k for k, v in SCHEMAS.items() if v.get('common')}
BLUF_RED_TAGS = {'請示', '行動', '決議'}

def schema_of(p):
    s = dict(COMMON) if SCHEMAS[p].get('common') else {}
    s.update(SCHEMAS[p]['slots'])
    return s

# ─────────────────────────── 渲染 ───────────────────────────

def head_html(pg, title_required=True):
    kick = pg.get('kicker')
    k = f'<span class="kicker"><span class="pip"></span>{fmt(kick)}</span>' if kick else ''
    t = pg.get('title')
    th = f'<h2 class="title">{fmt(t)}</h2><div class="rule"></div>' if t else ''
    if not (k or th):
        return ''
    return f'    <div class="head reveal">{k}{th}</div>\n'

def bluf_html(pg):
    v = pg.get('bluf')
    if not v:
        if pg.pattern in CONTENT_PATTERNS and pg.pattern != 'blank':
            warn(f'頁 {pg.no}（{pg.pattern}）沒有 bluf 結論列——內容頁建議必填（writing.md §〇）')
        return ''
    parts = split(v)
    tag, text = ('結論', parts[0]) if len(parts) == 1 else (parts[0], SEP.join(parts[1:]))
    act = ' red' if tag in BLUF_RED_TAGS else ''
    return f'    <div class="bluf{act} reveal" data-tag="{esc(tag)}">{fmt(text)}</div>\n'

def render_cover(pg):
    return (f'    <span class="logo-top" role="img" aria-label="永豐金控 SinoPac Holdings"></span>\n'
            f'    <div class="lines"><i></i><i></i><i></i></div>\n'
            f'    <div class="ct reveal">{fmt(pg.get("ct",""))}</div>\n'
            f'    <div class="crule"></div>\n'
            f'    <div class="who reveal">{fmt(pg.get("who",""))}</div>\n'
            f'    <div class="date reveal">{fmt(pg.get("date",""))}</div>\n'
            f'    <div class="foot"><span class="tag"><span class="zh">翻轉金融 共創美好生活</span>'
            f'<span class="en">Together, a better life.</span></span></div>\n')

def render_agenda(pg):
    items = pg.all('item')
    if not 3 <= len(items) <= 8:
        warn(f'頁 {pg.no}：agenda 建議 3–8 項（目前 {len(items)}）')
    rows = []
    for i, it in enumerate(items, 1):
        t, s = split(it, 2)
        sub = f'<div class="s">{fmt(s)}</div>' if s else ''
        rows.append(f'      <div class="ag"><span class="no">{i:02d}</span>'
                    f'<div><div class="t">{fmt(t)}</div>{sub}</div></div>')
    kick = pg.get('kicker', 'Agenda'); title = pg.get('title', '今日議程')
    head = (f'    <div class="head reveal"><span class="kicker"><span class="pip"></span>{fmt(kick)}</span>'
            f'<h2 class="title">{fmt(title)}</h2><div class="rule"></div></div>\n')
    return head + '    <div class="agenda reveal">\n' + '\n'.join(rows) + '\n    </div>\n'

def render_divider(pg):
    dx = pg.get('dx')
    dxh = f'    <p class="dx reveal">{fmt(dx)}</p>\n' if dx else ''
    return (f'    <div class="num reveal">{esc(pg.get("num",""))}</div>\n'
            f'    <div class="dt reveal">{fmt(pg.get("dt",""))}</div>\n'
            f'    <div class="rule"></div>\n{dxh}')

def _panel(pg, side, cls):
    chip, name, nm = split(pg.get(side, ''), 3)
    lis = []
    default_ic = '×' if side == 'a' else '✓'
    items = pg.all(f'{side}.li')
    if not 1 <= len(items) <= 5:
        warn(f'頁 {pg.no}：compare 每側 1–5 條（{side} 目前 {len(items)}）')
    for it in items:
        parts = split(it)
        ic, txt = (default_ic, parts[0]) if len(parts) == 1 else (parts[0], SEP.join(parts[1:]))
        lis.append(f'          <li><span class="ic">{esc(ic)}</span><span>{fmt(txt)}</span></li>')
    nmh = f'\n        <p class="nm">{fmt(nm)}</p>' if nm else ''
    return (f'      <div class="cpanel {cls}">\n'
            f'        <div class="ph"><span class="t">{esc(chip)}</span><span class="cl">{fmt(name)}</span></div>{nmh}\n'
            f'        <ul class="clist">\n' + '\n'.join(lis) + '\n        </ul>\n      </div>')

def render_compare(pg):
    return ('    <div class="compare reveal">\n'
            + _panel(pg, 'a', 'a') + '\n' + _panel(pg, 'b', 'b')
            + '\n    </div>\n')

def _grid_classes(base, flag_list, pg):
    n = len(flag_list)
    cls = base
    if n == 3:
        cls += ' n3'
    elif n != 4:
        warn(f'頁 {pg.no}：{base} 建議 3–4 格（目前 {n}）')
    leads = [i for i, fl in enumerate(flag_list) if 'lead' in fl.split()]
    if leads:
        if leads != [0]:
            die(f'頁 {pg.no}：lead 只能標在第一格（主從版的視覺主角固定放左上）')
        cls += ' has-lead'
    return cls

def render_cards(pg):
    items = [split(c, 6) for c in pg.all('card')]
    cls = _grid_classes('acts', [f[5] for f in items], pg)
    out = []
    for f in items:
        name, en, hint, detail, hot, flags = f
        fl = flags.split()
        c = ' blue' if 'blue' in fl else ''
        c += ' is-lead' if 'lead' in fl else ''
        hot_h = f'<span class="hot">{fmt(hot)}</span>' if hot else ''
        en_h = f'<div class="en">{esc(en)}</div>' if en else ''
        hint_h = f'<div class="hint">{fmt(hint)}</div>' if hint else ''
        out.append(f'      <div class="act{c}"><div class="stripe"></div>{en_h}<h3>{fmt(name)}</h3>'
                   f'{hint_h}<div class="detail">{fmt(detail)}</div>{hot_h}</div>')
    return f'    <div class="{cls} reveal">\n' + '\n'.join(out) + '\n    </div>\n'

_NUM = re.compile(r'^-?[\d,]+(\.\d+)?$')

def _kpi_value(v):
    if not _NUM.match(v):
        return f'<span>{esc(v)}</span>'
    neg = v.startswith('-')
    num = v.lstrip('-').replace(',', '')
    dec = len(num.split('.')[1]) if '.' in num else 0
    d = f' data-dec="{dec}"' if dec else ''
    return ('-' if neg else '') + f'<span data-count="{num}"{d}>0</span>'

def render_kpi(pg):
    items = [split(k, 6) for k in pg.all('kpi')]
    cls = _grid_classes('kpis', [f[5] for f in items], pg)
    out = []
    for v, unit, label, desc, trend, flags in items:
        fl = flags.split()
        c = ' blue' if 'blue' in fl else ''
        c += ' is-lead' if 'lead' in fl else ''
        u = f'<span class="u">{esc(unit)}</span>' if unit else ''
        d = f'<div class="d">{fmt(desc)}</div>' if desc else ''
        tr = ''
        if trend:
            m = re.match(r'^(up|dn)\s+(.*)$', trend)
            if not m:
                die(f'頁 {pg.no}：kpi 趨勢應為「up 文字」或「dn 文字」：{trend}')
            arrow = '▲' if m.group(1) == 'up' else '▼'
            tr = f'<span class="tr {m.group(1)}">{arrow} {fmt(m.group(2))}</span>'
        out.append(f'      <div class="kpi{c}"><div class="v">{_kpi_value(v)}{u}</div>'
                   f'<div class="l">{fmt(label)}</div>{d}{tr}</div>')
    return f'    <div class="{cls} reveal">\n' + '\n'.join(out) + '\n    </div>\n'

_CHIP = {'ok': 'ok', 'run': 'run', 'warn': 'warn'}

def _cell(txt, first=False):
    m = re.match(r'^(ok|run|warn):(.*)$', txt)
    if m:
        return f'<td><span class="st {_CHIP[m.group(1)]}">{fmt(m.group(2))}</span></td>'
    return f'<td class="em">{fmt(txt)}</td>' if first else f'<td>{fmt(txt)}</td>'

def render_table(pg):
    ths = split(pg.get('th', ''))
    rows = pg.all('row')
    if len(rows) > 7:
        warn(f'頁 {pg.no}：表格 {len(rows)} 列超過 7 列——拆頁、砍列或設 scroll: 1')
    th_h = ''.join(f'<th>{fmt(t)}</th>' for t in ths)
    body = []
    for r in rows:
        cells = split(r)
        if len(cells) != len(ths):
            warn(f'頁 {pg.no}：資料列欄數 {len(cells)} ≠ 表頭 {len(ths)}：{r[:24]}')
        body.append('          <tr>' + ''.join(_cell(c, i == 0) for i, c in enumerate(cells)) + '</tr>')
    return ('    <div class="tblwrap reveal">\n      <table>\n'
            f'        <thead><tr>{th_h}</tr></thead>\n        <tbody>\n'
            + '\n'.join(body) + '\n        </tbody>\n      </table>\n    </div>\n')

def render_matrix(pg):
    qs = pg.all('q')
    if len(qs) != 4:
        die(f'頁 {pg.no}：matrix 需恰 4 個 q（左上｜右上｜左下｜右下），目前 {len(qs)}')
    qh = []
    for q in qs:
        style, qt, qx = split(q, 3)
        if style not in ('hot', 'cool', 'soft', 'plain'):
            die(f'頁 {pg.no}：matrix 樣式需 hot/cool/soft/plain：{style}')
        qh.append(f'      <div class="q {style}"><div class="qt">{fmt(qt)}</div><div class="qx">{fmt(qx)}</div></div>')
    return ('    <div class="mx reveal">\n'
            f'      <div class="yaxis">{fmt(pg.get("y",""))}</div>\n'
            + '\n'.join(qh[:2]) + '\n'
            + '\n'.join(qh[2:]) + '\n'
            f'      <div class="xaxis">{fmt(pg.get("x",""))}</div>\n    </div>\n')

def render_case(pg):
    cmd = pg.get('cmd')
    right = []
    if cmd:
        label = pg.get('cmd-label', '指令')
        right.append(
            '        <div class="minlbl">操作示意</div>\n'
            f'        <div class="cmd"><button class="copy-btn">複製</button>'
            f'<div class="cmd-top"><span class="d"></span><span class="d"></span><span class="d"></span>'
            f'<span class="label">{esc(label)}</span></div><code>{fmt(cmd)}</code></div>')
    right.append(f'        <div class="out"><span class="ar">產出 ▸</span> {fmt(pg.get("out",""))}</div>')
    right.append(f'        <div class="why">{fmt(pg.get("why",""))}</div>')
    return ('    <div class="scn-grid reveal">\n      <div class="scn-col">\n'
            f'        <div class="minlbl">背景／痛點</div>\n        <div class="ba-old">{fmt(pg.get("bg",""))}</div>\n'
            f'        <div class="minlbl">做法</div>\n        <div class="ba-new">{fmt(pg.get("how",""))}</div>\n'
            '      </div>\n      <div class="scn-col">\n' + '\n'.join(right) + '\n      </div>\n    </div>\n')

def render_timeline(pg):
    steps = pg.all('step')
    if not 3 <= len(steps) <= 5:
        warn(f'頁 {pg.no}：timeline 建議 3–5 步（目前 {len(steps)}）')
    out = []
    for i, s in enumerate(steps):
        tag, name, desc, now = split(s, 4)
        cls = ' now' if now == 'now' else ''
        arr = '<span class="arr">→</span>' if i < len(steps) - 1 else ''
        out.append(f'      <div class="fstep{cls}"><span class="ftag">{fmt(tag)}</span>'
                   f'<span class="ft">{fmt(name)}</span><span class="fx">{fmt(desc)}</span>{arr}</div>')
    return '    <div class="flow-row reveal">\n' + '\n'.join(out) + '\n    </div>\n'

def render_optiontabs(pg):
    # tab.* 槽位以「第 i 個 tab 對第 i 個 tab.body/pro/con/acc」歸戶
    n_tabs = len(pg.all('tab'))
    if not 2 <= n_tabs <= 4:
        warn(f'頁 {pg.no}：optiontabs 建議 2–4 個頁籤（目前 {n_tabs}）')
    bodies, pros, cons, accs = pg.all('tab.body'), pg.all('tab.pro'), pg.all('tab.con'), pg.all('tab.acc')
    if len(bodies) != n_tabs:
        die(f'頁 {pg.no}：tab.body 數（{len(bodies)}）需等於 tab 數（{n_tabs}）')
    btns, panes = [], []
    for i, t in enumerate(pg.all('tab')):
        tn, name, sub = split(t, 3)
        on = ' class="on"' if i == 0 else ''
        btns.append(f'      <button{on} data-opt="{i}"><span class="tn">{esc(tn)}</span>{fmt(name)}</button>')
        meta = []
        if i < len(pros) and pros[i]:
            lis = ''.join(f'<li>{fmt(x)}</li>' for x in split(pros[i]))
            meta.append(f'          <div class="mbox pro"><div class="mh">優勢</div><ul>{lis}</ul></div>')
        if i < len(cons) and cons[i]:
            lis = ''.join(f'<li>{fmt(x)}</li>' for x in split(cons[i]))
            meta.append(f'          <div class="mbox con"><div class="mh">取捨</div><ul>{lis}</ul></div>')
        if i < len(accs) and accs[i]:
            at, ab = split(accs[i], 2)
            meta.append(f'          <details><summary><span class="dot"></span>{fmt(at)}'
                        f'<span class="chev">▸</span></summary><div class="body">{fmt(ab)}</div></details>')
        sub_h = f'<div class="od">{esc(sub)}</div>' if sub else ''
        panes.append(
            f'    <div class="tabpane{" on" if i == 0 else ""} reveal" data-pane="{i}">\n'
            f'      <div class="opt">\n        <div class="omain">\n'
            f'          <div class="ot">{fmt(name)}</div>{sub_h}\n'
            f'          <p class="ob">{fmt(bodies[i])}</p>\n        </div>\n'
            f'        <div class="ometa">\n' + '\n'.join(meta) + '\n        </div>\n      </div>\n    </div>')
    return ('    <div class="tabs reveal">\n' + '\n'.join(btns) + '\n    </div>\n'
            + '\n'.join(panes) + '\n')

def render_quote(pg):
    kick = pg.get('kicker', '核心觀點')
    by = pg.get('by')
    by_h = f'    <div class="qby reveal">{fmt(by)}</div>\n' if by else ''
    return (f'    <div class="head reveal"><span class="kicker"><span class="pip"></span>{fmt(kick)}</span></div>\n'
            f'    <div class="bigq reveal">{fmt(pg.get("q",""))}</div>\n' + by_h)

def render_prose(pg):
    ps = pg.all('p')
    if not 2 <= len(ps) <= 10:
        warn(f'頁 {pg.no}：prose 建議 2–10 段（目前 {len(ps)}）')
    body = '\n'.join(f'      <p>{fmt(p)}</p>' for p in ps)
    return '    <div class="prose reveal">\n' + body + '\n    </div>\n'

def render_ask(pg):
    items = pg.all('item')
    if not 2 <= len(items) <= 4:
        warn(f'頁 {pg.no}：ask 建議 2–4 條請示事項（目前 {len(items)}）')
    lis = []
    for i, it in enumerate(items, 1):
        at, ax = split(it, 2)
        ax_h = f'<div class="ax">{fmt(ax)}</div>' if ax else ''
        lis.append(f'        <div class="ask-item"><span class="no">{i:02d}</span>'
                   f'<div><div class="at">{fmt(at)}</div>{ax_h}</div></div>')
    facts = []
    for f in pg.all('fact')[:4]:
        v, u, l = split(f, 3)
        u_h = f'<span class="u">{esc(u)}</span>' if u else ''
        facts.append(f'        <div class="s"><div class="n">{esc(v)}{u_h}</div><div class="l">{fmt(l)}</div></div>')
    side = ('      <div class="side">\n' + '\n'.join(facts) + '\n      </div>\n') if facts else ''
    return ('    <div class="ask reveal">\n      <div class="ask-list">\n'
            + '\n'.join(lis) + '\n      </div>\n' + side + '    </div>\n')

def render_blank(pg):
    inner = pg.raw.get('html', '')
    return '    <div class="canvas reveal">\n' + inner + '\n    </div>\n'

def render_closing(pg):
    sub = pg.get('sub')
    sub_h = f'    <p class="sub reveal">{fmt(sub)}</p>\n' if sub else ''
    return ('    <span class="logo-chip reveal"><span class="logo"></span></span>\n'
            '    <div class="cline reveal"><i></i><u></u></div>\n'
            f'    <p class="quote reveal">{fmt(pg.get("q",""))}</p>\n' + sub_h +
            '    <div class="foot"><span class="tag"><span class="zh">翻轉金融 共創美好生活</span>'
            '<span class="en">Together, a better life.</span></span></div>\n')

RENDER = {
    'cover': render_cover, 'agenda': render_agenda, 'divider': render_divider,
    'compare': render_compare, 'cards': render_cards, 'kpi': render_kpi,
    'table': render_table, 'matrix': render_matrix, 'case': render_case,
    'timeline': render_timeline, 'optiontabs': render_optiontabs,
    'quote': render_quote, 'prose': render_prose, 'ask': render_ask,
    'blank': render_blank, 'closing': render_closing,
}
SECTION_CLASS = {'cover': ' cover', 'divider': ' divider', 'quote': ' quote-slide', 'closing': ' closing'}
NO_HEAD = {'cover', 'agenda', 'divider', 'quote', 'closing'}   # 這些版型自帶頁首/不用標準 head

def render_page(pg, first):
    if pg.pattern not in RENDER:
        die(f'頁 {pg.no}：未知版型「{pg.pattern}」；可用：{", ".join(sorted(RENDER))}')
    schema = schema_of(pg.pattern)
    for key in list(pg.slots) + list(pg.raw):
        if key not in schema:
            die(f'頁 {pg.no}（{pg.pattern}）：未知槽位「{key}」；可用：{", ".join(schema)}\n'
                f'  （查格式：python3 build_deck.py --schema {pg.pattern}）')
    for key, (req, _, doc) in schema.items():
        if req and key not in pg.slots and key not in pg.raw:
            die(f'頁 {pg.no}（{pg.pattern}）：缺必填槽位「{key}」＝{doc}')
    body = ''
    if pg.pattern not in NO_HEAD:
        body += head_html(pg)
        body += bluf_html(pg)
    body += RENDER[pg.pattern](pg)
    cls = SECTION_CLASS.get(pg.pattern, '')
    active = ' active' if first else ''
    scroll = ' scroll' if pg.get('scroll') == '1' else ''
    return (f'<section class="slide{cls}{active}" data-label="{esc(pg.label)}">\n'
            f'  <div class="frame"><div class="inner{scroll}">\n{body}  </div></div>\n</section>\n')

# ─────────────────────────── 主程式 ───────────────────────────

def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('content', nargs='?', help='content.md 路徑')
    ap.add_argument('-o', '--out', default='deck.html')
    ap.add_argument('--template', default=str(TEMPLATE))
    ap.add_argument('--check', action='store_true', help='只驗證不輸出')
    ap.add_argument('--list', action='store_true', help='列出全部版型')
    ap.add_argument('--schema', metavar='PATTERN', help='查單一版型槽位')
    a = ap.parse_args()

    if a.list:
        for name in SCHEMAS:
            print(f'{name:<11}{SCHEMAS[name]["desc"]}')
        return
    if a.schema:
        if a.schema not in SCHEMAS:
            die(f'未知版型「{a.schema}」；可用：{", ".join(SCHEMAS)}')
        print(f'## N｜{a.schema}｜<data-label>　—　{SCHEMAS[a.schema]["desc"]}')
        for key, (req, rep, doc) in schema_of(a.schema).items():
            mark = '必填' if req else '選用'
            mark += '·可重複' if rep else ''
            print(f'  {key:<10}[{mark}] {doc}')
        return
    if not a.content:
        ap.error('缺 content.md（或用 --list / --schema）')

    meta, pages, custom_css = parse(a.content)
    if not pages:
        die('content.md 沒有任何「## 頁碼｜版型｜標籤」頁面')

    tpl = Path(a.template).read_text(encoding='utf-8')
    cut = tpl.index('<!-- ============ PATTERN')
    prefix = tpl[:cut]
    suffix = tpl[tpl.index('<script>'):]

    if meta.get('title'):
        prefix = re.sub(r'<title>.*?</title>', f'<title>{esc(meta["title"])}</title>', prefix, 1)
    if custom_css:
        suffix = suffix.replace('<style id="deck-custom">/* 本副簡報專屬樣式寫在這裡；禁止改動上方引擎 */</style>',
                                f'<style id="deck-custom">\n{custom_css}\n</style>')

    sections = '\n'.join(render_page(pg, i == 0) for i, pg in enumerate(pages))
    out_html = prefix + sections + '\n' + suffix

    leftovers = re.findall(r'簡報標題|○○部門|一句話說明|Year / Month', sections)
    if leftovers:
        warn(f'疑似占位字殘留：{set(leftovers)}')

    if a.check:
        print(f'[build_deck] 驗證通過：{len(pages)} 頁，警告 {len(WARNINGS)} 則')
        return
    Path(a.out).write_text(out_html, encoding='utf-8')
    print(f'[build_deck] 已輸出 {a.out}：{len(pages)} 頁（{len(out_html)//1024} KB），警告 {len(WARNINGS)} 則')
    print('[build_deck] 驗收：開 deck.html?debug 看溢出告警；跑 lint_content.py 查字數/行數')

if __name__ == '__main__':
    main()
