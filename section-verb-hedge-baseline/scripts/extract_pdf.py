"""
PDF 논문 → 분석용 문장 TXT + 구조 TSV + 사람 확인 목록 (ACS 2단 편집 기준, 글자 단위 프로토타입)
사용: python3 extract_pdf.py <pdf> <document_id> <out_dir>

맥주 논문(XML 경로)에서 가져온 원칙
- 본문만: 제목·저자·소속·캡션·표·각주·참고문헌·여백 문구를 뺀다. 글자 크기가 본문 크기인 줄만 남긴다.
- 인용 복원: 본문보다 작고 위로 올라간 글자 묶음 가운데 인용으로 판단되는 것만 [n]으로 바꾼다.
  지수(10^5), 전하(2+), 단위 지수(cm−1), 앞붙은 위첨자(1H, 3MC)는 인용으로 바꾸지 않는다.
- 인용 번호가 마침표 뒤에 오면 앞 문장에 붙인다. 문단 경계를 넘어 문장을 잇지 않는다.
- 번호 없는 절 제목은 절 순서 번호로 문장 ID를 만든다(초록 0, 이후 1, 2, …).
- 수식 줄은 본문에서 빼고 [EQ n]을 남기며 원문은 보고서에 보관한다.
- NMR·원소분석 같은 비문장 데이터는 prose=false로 표시한다(지우지 않음).
- 여백의 'Downloaded from … by <기관> user on …'(회전 글자)은 지우고 개수를 기록한다.
"""
import sys, os, re, csv, json, hashlib, statistics, unicodedata, subprocess
from collections import Counter, defaultdict
import pdfplumber

VERSION = "pdf-extract-0.4.7"
# 일부 2011년 이전 ACS PDF의 수식용 글꼴(AdvP4C4E74 등)은 기호를 다른 글자에 대응시켜 둔다
# (cid:1): 범위 인용(13−15)의 줄표가 유니코드 대응 없이 나오는 경우(cm1031656)
FONT_MAP = {'AdvP4C4E74': {'ð': '(', 'Þ': ')', '¼': '=', 'þ': '+', 'À': '−', '': '−', '(cid:1)': '−', '0': '′'},
            'AdvP4C4E59': {'þ': '+', 'À': '−', '¼': '=', 'ð': '(', 'Þ': ')'},
            'AdvP4C4E46': {'þ': '+', 'À': '−', '¼': '=', 'ð': '(', 'Þ': ')'}}
GEN_MAP = {'\u200b': '', 'ﬁ': 'fi', 'ﬂ': 'fl', 'ﬀ': 'ff', 'ﬃ': 'ffi', 'ﬄ': 'ffl'}
HEAD_RE = re.compile(r'^[■’\s]*(?:\d+\.\s*)?(INTRODUCTION|EXPERIMENTAL(?: SECTION| PROCEDURES)?|COMPUTATIONAL (?:DETAILS|METHODS|SECTION)|'
                     r'Computational (?:Details|Methods)|RESULTS AND DISCUSSION|RESULTS|DISCUSSION|'
                     r'CONCLUSIONS?|REMARKS AND CONCLUSIONS|ASSOCIATED CONTENT|AUTHOR INFORMATION|ACKNOWLEDGMENTS?|ACKNOWLEDGMENT|REFERENCES|'
                     r'Introduction|Experimental(?: Section)?|Results and Discussion|Conclusions?)\s*$')
TYPE = {'INTRODUCTION': 'INT', 'EXPERIMENTAL': 'MET', 'COMPUTATIONAL DETAILS': 'MET', 'COMPUTATIONAL METHODS': 'MET', 'COMPUTATIONAL': 'MET',
        'RESULTS AND DISCUSSION': 'RD', 'RESULTS': 'RES', 'DISCUSSION': 'DIS',
        'CONCLUSION': 'CON', 'CONCLUSIONS': 'CON', 'REMARKS AND CONCLUSIONS': 'CON'}
END = {'ASSOCIATED CONTENT', 'AUTHOR INFORMATION', 'ACKNOWLEDGMENT', 'ACKNOWLEDGMENTS', 'REFERENCES'}
ABBR = {'al', 'e.g', 'i.e', 'ca', 'vs', 'Fig', 'Figs', 'eq', 'eqs', 'ref', 'refs', 'Ref', 'Refs', 'approx', 'No', 'cf', 'resp', 'Eq', 'Prof', 'Dr', 'viz', 'Anal', 'Calcd', 'calcd', 'equiv'}
NONPROSE = re.compile(r'δ\s*[\d−-]|\bppm\b|\d\s*MHz|Anal\.\s*Calc|\bCalcd\b|HRMS|\bIR,\s*KBr|m/z|\bJ\s*=|\d[A-Z]{1,2}\s*=\s*\d|\(\s*[sdtqm],\s*\d+H|ν\s*[A-Z]|\bFound:\s*C,|\d+H,\s*ArH')
SYMBOL_FONTS = re.compile(r'(^|\+)(03|20|22|fb|STIX|Adv(P4|symbol|Els))')
DROP_LINE = re.compile(r'^(Received|Revised|Accepted|Published)\b|Special Issue|American Chemical Society|^pubs\.acs|^dx\.doi|^DOI:'
                       r'|\bVol\.\s*\d+,\s*No\.\s*\d+|^(\d{1,5}\s+)?\S[^.]{0,30} et al\.(\s+\d{1,5})?$')   # 2010년 무렵 ACS 쪽 머리글("Inorganic Chemistry, Vol. 49, No. 5, 2010", "2048 Yang et al.")

def fam(fn): return fn.split('+')[-1]
def font_base(f): return re.sub(r'[-,](b|i|bi|Bold|Italic|BoldItalic|Semibold)$', '', f)   # AdvTimes-b, AdvTimes-i → AdvTimes

def split_sents(t):
    out, start = [], 0
    for m in re.finditer(r'[.!?](\s*\[[\d,–]+\])?\s+(?=[A-Z(“"\[]|\d+[A-Za-z])', t):
        pre = t[start:m.start() + 1]
        lw = re.search(r'([A-Za-z][A-Za-z.]*)\.$', pre)
        if lw and (lw.group(1).rstrip('.') in ABBR or re.fullmatch(r'[A-Z]', lw.group(1))): continue
        end = m.end(1) if m.group(1) else m.start() + 1
        out.append(t[start:end].strip()); start = m.end()
    if t[start:].strip(): out.append(t[start:].strip())
    return out

def main(pdf_path, doc_id, out_dir):
    os.makedirs(out_dir, exist_ok=True)
    review, equations = [], []
    pdf = pdfplumber.open(pdf_path)
    removed_margin = 0
    P = []
    for pi, page in enumerate(pdf.pages):
        cs = []
        for c in page.chars:
            if not c['upright']: removed_margin += 1; continue
            t = c['text']
            mp = FONT_MAP.get(fam(c['fontname']))
            if mp and t in mp: t = mp[t]
            t = GEN_MAP.get(t, t)
            if not t.strip(): continue
            cs.append(dict(c, text=t, f=fam(c['fontname']), base=page.height - c['matrix'][5]))
        P.append((page, cs))
    allc = [c for _, cs in P for c in cs]
    sizes = Counter(round(c['size'], 1) for _, cs in P[1:] for c in cs).most_common(2)
    body_size = sizes[0][0]
    # 실험 절(본문보다 한 단계 작은 글자)이 길면 그 크기가 가장 많을 수 있다(jo2012384: 9 pt 30,504자, 10 pt 28,998자).
    # 비슷하게 많고 0.5~1.5 pt 큰 크기가 있으면 그것을 본문으로 본다
    if len(sizes) > 1 and sizes[1][1] >= .6 * sizes[0][1] and .5 <= sizes[1][0] - sizes[0][0] <= 1.5: body_size = sizes[1][0]
    main_font = Counter(c['f'] for _, cs in P[1:] for c in cs if abs(c['size'] - body_size) < .3).most_common(1)[0][0]
    # 참고문헌 수: pdftotext 전문에서 REFERENCES 뒤 '(n) ' 줄(검증 스크립트와 같은 방식)
    try:
        # 인코딩을 정하지 않으면 한국어 Windows(cp949)에서 UnicodeDecodeError로 멈춘다(v1 보고서). poppler 출력을 UTF-8로 고정해 읽는다
        full = subprocess.run(['pdftotext', '-enc', 'UTF-8', pdf_path, '-'], capture_output=True, text=True, encoding='utf-8', errors='replace').stdout
    except (FileNotFoundError, OSError):   # pdftotext(poppler)가 없으면 pdfplumber로
        full = '\n'.join((p_.extract_text() or '') for p_, _ in P)
    cut = re.search(r'\n■?\s*REFERENCES\s*\n', full)
    nums = [int(x) for x in re.findall(r'(?m)^\((\d{1,3})\)\s', full[cut.end():] if cut else full)]
    max_ref = max(nums) if nums else 300

    def make_lines(cs, region):
        """글자를 줄로: 본문 크기 범위 글자로 줄을 만들고 작은 글자를 위/아래 첨자로 붙인다."""
        # 2010년형 'Å': 'A' 위에 따로 찍힌 고리(˚)를 합친다
        rings = [c for c in cs if c['text'] in '˚']
        for r in rings:
            a = [c for c in cs if c['text'] == 'A' and abs((c['x0'] + c['x1']) / 2 - (r['x0'] + r['x1']) / 2) < 3 and 0 < c['base'] - r['base'] < 9]
            if a: a[0]['text'] = 'Å'
        cs = [c for c in cs if c['text'] != '˚']
        norm_c = [c for c in cs if body_size * .85 <= c['size'] <= body_size * 1.25]
        small = [c for c in cs if c['size'] < body_size * .85]
        bigc = [c for c in cs if c['size'] > body_size * 1.25]
        norm_c.sort(key=lambda c: (c['base'], c['x0']))
        lines = []
        for c in norm_c:
            if lines and abs(c['base'] - lines[-1]['base']) < 1.6: lines[-1]['cs'].append(c)
            else: lines.append(dict(base=c['base'], cs=[c]))
        for ln in lines:
            ln['base'] = statistics.median(c['base'] for c in ln['cs'])
            ln['x0'] = min(c['x0'] for c in ln['cs']); ln['x1'] = max(c['x1'] for c in ln['cs'])
        for c in sorted(small, key=lambda c: c['x0']):
            cand = [ln for ln in lines if -5.5 < c['base'] - ln['base'] < 3.5 and ln['x0'] - 4 <= c['x0'] <= ln['x1'] + 8]
            if not cand: continue
            ln = min(cand, key=lambda l: abs(l['base'] - c['base']) + (0 if c['base'] <= l['base'] + 3.5 else 9))
            d = c['base'] - ln['base']
            c = dict(c, role='sup' if d < -1.0 else ('sub' if d > 0.8 else 'n')); ln['cs'].append(c)
            ln['x1'] = max(ln['x1'], c['x1'])
        for ln in lines:
            ln['cs'].sort(key=lambda c: c['x0'])
            ln['top'] = ln['base'] - body_size
            # 2010년형: 'Å'이 'A'와 그 위의 고리(˚)로 따로 찍힌 경우 합친다
            rings = [c for c in ln['cs'] if c['text'] in '˚°' and c.get('role') == 'sup']
            for r in rings:
                a = [c for c in ln['cs'] if c['text'] == 'A' and abs((c['x0'] + c['x1']) / 2 - (r['x0'] + r['x1']) / 2) < 2.5]
                if a: a[0]['text'] = 'Å'; ln['cs'].remove(r)
        return lines, bigc

    def tokens(ln):
        """줄 안 글자를 덩어리로(같은 역할이고 붙어 있는 글자끼리)."""
        toks = []
        for c in ln['cs']:
            role = c.get('role', 'n')
            if toks and toks[-1]['role'] == role and c['x0'] - toks[-1]['x1'] < (0.9 if role == 'n' else 1.2) and not (role == 'n' and c['x0'] - toks[-1]['x1'] > 0.9):
                toks[-1]['text'] += c['text']; toks[-1]['x1'] = c['x1']; toks[-1]['fonts'].add(c['f'])
            else:
                toks.append(dict(role=role, text=c['text'], x0=c['x0'], x1=c['x1'], fonts={c['f']}, size=c['size']))
        return toks

    def render(toks, ctx):
        out, prev = '', None
        for i, t in enumerate(toks):
            gap = t['x0'] - prev['x1'] if prev else 99
            nxt = toks[i + 1] if i + 1 < len(toks) else None
            if t['role'] == 'sup':
                tt = t['text'].replace('−', '–').replace('-', '–')
                attached_next = nxt is not None and nxt['role'] == 'n' and nxt['x0'] - t['x1'] < 0.9 and re.match(r'[A-Za-z]', nxt['text'])
                ptxt = prev['text'] if prev else ''
                cite_like = re.fullmatch(r'\d+[a-z]?(?:[,–]\d+[a-z]?)*,?', tt) is not None
                if cite_like and not attached_next and not re.search(r'(^|×)10$', ptxt):
                    ns = []
                    for part in tt.strip(',').split(','):
                        part = re.sub(r'(?<=\d)[a-z]', '', part)
                        r_ = re.fullmatch(r'(\d+)–(\d+)', part)
                        ns += list(range(int(r_.group(1)), int(r_.group(2)) + 1)) if r_ else ([int(part)] if part.isdigit() else [])
                    if ns and max(ns) <= max_ref:
                        clean = re.sub(r'(?<=\d)[a-z]', '', tt.strip(','))
                        if clean != tt.strip(','):
                            review.append(dict(type='글자 꼬리표 인용', where=ctx, original=t['text'], rendered='[' + clean + ']', note='분석용 번호만 남김(26a→26)'))
                        out += ('' if gap < 3 else ' ') + '[' + clean + ']'
                    else:
                        out += t['text']; review.append(dict(type='위첨자 숫자(인용 아님: 번호 범위 밖)', where=ctx, original=ptxt + '^' + t['text'], rendered=ptxt + t['text'], note=f'참고문헌 최대 {max_ref}'))
                elif cite_like and re.search(r'(^|×)10$', ptxt):
                    out += '^' + t['text']
                elif attached_next:
                    out += ('' if gap < 1.2 else ' ') + t['text']    # 1H, 3MC: 다음 낱말 앞에 붙임
                else:
                    out += t['text']                                    # 전하(2+), 단위 지수(−1) 등
            elif t['role'] == 'sub':
                out += t['text']
            else:
                sep = ''
                if prev is not None:
                    if prev['role'] == 'n': sep = ' ' if gap > 0.9 else ''
                    elif prev['role'] == 'sub': sep = ' ' if gap > 0.8 else ''
                    else:  # 앞이 위첨자
                        sep = '' if (out.endswith(']') is False and gap < 0.9) else (' ' if gap > 0.9 else '')
                out += sep + t['text']
            prev = t
        return re.sub(r'\s+', ' ', out).strip()

    # 1) 쪽·단별 줄
    lines_all, first_head = [], None
    for pi, (page, cs) in enumerate(P):
        mid = page.width / 2
        for col in (0, 1):
            cc = [c for c in cs if ((c['x0'] + c['x1']) / 2 < mid) == (col == 0)]
            lines, _ = make_lines(cc, 'body')
            for ln in lines:
                toks = tokens(ln)
                normal = [c for c in ln['cs'] if c.get('role', 'n') == 'n' and c['size'] >= body_size * .85]
                med = statistics.median(c['size'] for c in normal)
                plain = ' '.join(t['text'] for t in toks if t['role'] == 'n')
                hk = HEAD_RE.match(plain)
                main_share = sum(c['f'] == main_font for c in normal) / len(normal)
                # 실험 절에서 굵은 화합물 이름으로 시작하는 줄(jo902004n: "2-Hydroxy-…adamantane (10a):39 2.29 g")은
                # 본문 글꼴이 25%보다 적어 빠졌다. 줄 첫 글자가 본문 글꼴의 굵은체이면 같은 계열 글꼴을 본문으로 친다.
                # 기울임체는 제외한다(쪽 머리글 "Inorganic Chemistry, Vol. 49"가 본문에 섞여 문장이 쪽 경계에서 끊겼다, ic901600v)
                first_c = min(normal, key=lambda c: c['x0'])
                if main_share < .25 and re.search(r'[-,](b|Bold|Semibold)$', first_c['f']) and font_base(first_c['f']) == font_base(main_font):
                    main_share = sum(font_base(c['f']) == font_base(main_font) for c in normal) / len(normal)
                kind = 'other'
                if hk and med >= body_size - .3: kind = 'head'
                elif abs(med - body_size) < .35 and (main_share >= .25 or any(SYMBOL_FONTS.search(c['fontname']) for c in normal)) and not DROP_LINE.search(plain):
                    kind = 'body'
                elif body_size - 1.3 < med <= body_size - .35 and main_share >= .25 and not DROP_LINE.search(plain):
                    kind = 'body_small'   # ACS 실험 절은 본문보다 한 단계 작은 글자(9 pt)로 조판된다
                d = dict(page=pi, col=col, top=ln['top'], x0=ln['x0'], x1=ln['x1'], kind=kind, toks=toks, plain=plain,
                         head=(re.sub(r'\s+(SECTION|PROCEDURES)$', '', hk.group(1).upper()) if hk else None))
                lines_all.append(d)
                if kind == 'head' and first_head is None and pi == 0: first_head = d
    if first_head is None:
        hs = [l for l in lines_all if l['kind'] == 'head']
        first_head = hs[0] if hs else None
    # 2) 초록(첫 쪽, 첫 절 제목 위, 쪽 전체 폭)
    page0, cs0 = P[0]
    abs_text, abs_box = '', None
    box = lambda cs_: [min(c['x0'] for c in cs_), min(c['top'] for c in cs_), max(c['x1'] for c in cs_), max(c['bottom'] for c in cs_)] if cs_ else None
    if first_head and first_head['page'] == 0:
        lab = [c for c in cs0 if c['text'] == 'A' and ''.join(x['text'] for x in cs0[cs0.index(c):cs0.index(c) + 9]) == 'ABSTRACT:']
        if lab:
            y0 = lab[0]['top'] - 1; afont = None
            reg = [c for c in cs0 if y0 <= c['top'] < first_head['top'] - 2]
            after = [c for c in reg if c['top'] > y0 and abs(c['size'] - lab[0]['size']) < .3 and c['f'] != lab[0]['f']]
            afont = Counter(c['f'] for c in after).most_common(1)[0][0] if after else None
            keepf = {afont} | {c['f'] for c in reg if SYMBOL_FONTS.search(c['fontname'])}
            reg = [c for c in reg if c['f'] in keepf or c['size'] < body_size * .85]
            # 초록 상자 옆 그림(목차 그림) 글자 빼기: 초록 글꼴 글자의 x 범위 안만
            axs = [c for c in reg if c['f'] == afont]
            if axs:
                reg = [c for c in reg if c['x0'] >= min(c['x0'] for c in axs) - 2 and c['x1'] <= max(c['x1'] for c in axs) + 2]
            ls, _ = make_lines(reg, 'abs'); abs_box = box(reg)
            abs_lines = [render(tokens(l), 'p1 초록') for l in ls]
            if abs_lines: abs_lines[0] = re.sub(r'^ABSTRACT:\s*', '', abs_lines[0])
            abs_text = abs_lines
        else:
            rc = [l for l in lines_all if l['page'] == 0 and l['plain'].startswith('Received')]
            # 2010형: 쪽 전체 폭 상자(Received 줄 아래 ~ 첫 절 위)
            rtop = min((c['top'] for c in cs0 if ''.join(x['text'] for x in cs0[cs0.index(c):cs0.index(c) + 8]) == 'Received'), default=None)
            if rtop is not None:
                reg = [c for c in cs0 if rtop + 8 < c['top'] < first_head['top'] - 2]
                if reg:
                    # 초록 글자 크기가 본문과 다르면(jo902004n: 초록 10 pt, 본문 9.5 pt) 영역에서 가장 많은 글꼴로 잡는다
                    afont = (Counter(c['f'] for c in reg if abs(c['size'] - body_size) < .3) or Counter(c['f'] for c in reg)).most_common(1)[0][0]
                    ax = [c for c in reg if c['f'] == afont]
                    reg = [c for c in reg if min(x['x0'] for x in ax) - 2 <= c['x0'] <= max(x['x1'] for x in ax) + 2 and c['top'] <= max(x['bottom'] for x in ax) + 2]
                    ls, _ = make_lines(reg, 'abs'); abs_box = box(reg)
                    abs_text = [render(tokens(l), 'p1 초록') for l in ls]
    # 3) 본문 줄 순서와 문단
    body = [l for l in lines_all if not (l['page'] == 0 and first_head and first_head['page'] == 0 and l['top'] < first_head['top'] - 2)]
    body.sort(key=lambda l: (l['page'], l['col'], l['top']))
    body_ids = {id(l) for l in body}   # 절 끝(REFERENCES 등) 뒤 줄은 layout.json에서 END로 표시
    marg = defaultdict(list)
    for l in body:
        if l['kind'] in ('body', 'body_small'): marg[(l['page'], l['col'])].append(l['x0'])
    left = {k: Counter(round(x) for x in v).most_common(1)[0][0] for k, v in marg.items()}
    bl = [l for l in body if l['kind'] == 'body']
    pitch = statistics.median([b['top'] - a['top'] for a, b in zip(bl, bl[1:]) if a['page'] == b['page'] and a['col'] == b['col'] and 0 < b['top'] - a['top'] < 20] or [11])
    paras, cur_sec, cur_title, sub, para, prev, eqn = [], 'FRONT', '', '', None, None, 0
    pending_head, pending_para_open = '', False
    if abs_text: paras.append(dict(sec='ABS', title='ABSTRACT', page=0, lines=abs_text))
    for l in body:
        if l['kind'] == 'head':
            if l['head'] in END: l['sec'] = 'END'; break
            cur_sec = TYPE.get(l['head'], 'OTHER'); cur_title = l['head']; sub = ''; para = None; prev = None; pending_head = ''; l['sec'] = cur_sec; continue
        l['sec'] = cur_sec   # 검증 그림용(layout.json): 이 줄이 들어간 절
        if cur_sec == 'FRONT': continue
        if not (l['kind'] == 'body' or (l['kind'] == 'body_small' and cur_sec == 'MET')): continue
        l['used'] = True
        ctx = f"p{l['page'] + 1}"
        txt = render(l['toks'], ctx)
        eq_frag = (not re.search(r'[a-z]{4,}', txt) and len(txt) < 45 and not re.search(r'[.;,)]$', txt)
                   and (re.search(r'[=^∑Σ]|\(cid:\d+\)', txt) or not re.search(r'[a-z]{2,}', txt)))
        if eq_frag or (re.search(r'\(\d{1,2}\)\s*$', txt) and len(re.findall(r'\b[a-z]{4,}\b', txt)) <= 2 and (re.search(r'[=+→⇆⇌⇄−]', txt) or len(txt.split()) <= 6)):
            eqn += 1; equations.append(dict(n=eqn, page=l['page'] + 1, raw=txt))
            review.append(dict(type='수식 줄 제거', where=ctx, original=txt, rendered=f'[EQ {eqn}]', note='본문에서 빼고 자리표시'))
            if para: para['lines'].append(f'[EQ {eqn}]')
            prev = l; continue
        indent = l['x0'] - left.get((l['page'], l['col']), l['x0']) > 5
        gapv = prev is not None and prev['page'] == l['page'] and prev['col'] == l['col'] and l['top'] - prev['top'] > pitch * 1.7
        last_txt = para['lines'][-1] if para and para['lines'] else ''
        sentence_open = bool(last_txt) and not re.search(r'[.!?:]["”)]?\]?(\s*\[[\d,–]+\])?$', last_txt)
        toks = l['toks']
        first_n = next((t for t in toks if t['role'] == 'n'), None)
        starts_lower = bool(first_n and re.match(r'[a-z]', first_n['text']))
        new_para = para is None or (indent and not (sentence_open and starts_lower)) or (gapv and not sentence_open)
        # 끼움 소제목: 문단 첫머리의 본문 아닌 글꼴(굵게·기울임) 덩어리, 마침표·쌍점으로 끝남. 두 줄에 걸칠 수 있다.
        def is_head_tok(t):
            if t['role'] != 'n': return True
            if main_font in t['fonts']: return False
            if any(SYMBOL_FONTS.search('+' + f) for f in t['fonts']): return len(t['text']) <= 2 and not re.search(r'[A-Za-z0-9]', t['text'])
            return True
        if (new_para or pending_head) and first_n is not None and (pending_head or is_head_tok(first_n)):
            lead = []
            for t in toks:
                if not is_head_tok(t): break
                lead.append(t)
            cut_at = max([i for i, t in enumerate(lead) if t['role'] == 'n' and re.search(r'[.:]$', t['text'])] or [-1])
            if cut_at >= 0:
                head_txt = (pending_head + ' ' if pending_head else '') + render(lead[:cut_at + 1], ctx)
                pending_head = ''
                rest = toks[cut_at + 1:]
                # 바로 이어지는 두 번째 끼움 제목(기울임 소소제목)
                lead2 = []
                for t in rest:
                    if not is_head_tok(t): break
                    lead2.append(t)
                cut2 = max([i for i, t in enumerate(lead2) if t['role'] == 'n' and re.search(r'[.:]$', t['text'])] or [-1])
                if cut2 >= 0:
                    head_txt += ' / ' + render(lead2[:cut2 + 1], ctx); rest = rest[cut2 + 1:]
                if re.match(r'(Acknowledg|Supporting Information|Note Added)', head_txt): break
                sub = re.sub(r'(\w)- (\w)', r'\1\2', head_txt.rstrip('.:').replace('. /', ' /'))
                txt = render(rest, ctx)
                if pending_para_open:
                    new_para = True
                pending_para_open = False
                new_para = True
                if not txt: prev = l; para = None; continue
            elif len(lead) == len(toks):   # 줄 전체가 제목 글꼴이고 아직 끝나지 않음 → 다음 줄로 이어짐
                pending_head = (pending_head + ' ' if pending_head else '') + render(lead, ctx)
                pending_para_open = True; prev = l; continue
        if new_para:
            para = dict(sec=cur_sec, title=cur_title + (f' > {sub}' if sub else ''), page=l['page'], lines=[]); paras.append(para)
        elif prev is not None and (prev['page'] != l['page'] or prev['col'] != l['col'] or gapv):
            review.append(dict(type='단·쪽·그림 경계를 넘어 이음', where=ctx, original=last_txt[-60:] + ' ‖ ' + txt[:60], rendered='', note='앞 줄이 문장 끝이 아니어서 같은 문단으로 이음'))
        para['lines'].append(txt); prev = l
    # 4) 줄 끝 하이픈
    vocab = Counter(re.findall(r"[A-Za-z][A-Za-z\-]+", ' '.join(' '.join(p['lines']) for p in paras)))
    def join_lines(lines, ctx):
        s = ''
        for ln in lines:
            if not ln: continue
            m = re.search(r'([A-Za-z]+)-$', s)
            if m and re.match(r'[a-z]', ln):
                a, b = m.group(1), re.match(r'([a-z]+)', ln).group(1)
                pre_ch = s[-len(a) - 2] if len(s) > len(a) + 1 else ' '
                if re.match(r'[\d\])]', pre_ch) or re.search(r'[\d(\[]', s[-len(a) - 6:-1]):
                    s += ln   # 화학명(2-pyrazolyl-, 1,2-bis-)은 하이픈 유지
                elif vocab[a + b] >= vocab[a + '-' + b] and vocab[a + b] > 0: s = s[:-1] + ln
                elif vocab[a + '-' + b] > 0 or (len(a) >= 3 and vocab[a] > 0 and vocab[b] > 0 and len(b) >= 3 and b not in ('tion', 'sion', 'ment', 'ness', 'ing', 'ed', 'ity', 'ance', 'ence')): s += ln
                else:
                    s = s[:-1] + ln
                    review.append(dict(type='줄 끝 하이픈(근거 없음)', where=ctx, original=f'{a}- | {b}', rendered=a + b, note=f'문서에 {a+b}·{a}-{b} 모두 없음 → 붙여 씀'))
            elif re.search(r'[-–/]$', s) and re.match(r'[\dA-Za-z(]', ln) and s.endswith(('-', '–', '/')):
                s += ln
            else:
                s += (' ' if s else '') + ln
        return re.sub(r'\s+', ' ', s).strip()
    sec_no, sents, pnum = {}, [], 0
    for p in paras:
        text = join_lines(p['lines'], p['title'])
        if not text: continue
        pnum += 1
        major = p['title'].split(' > ')[0]
        if major not in sec_no: sec_no[major] = 0 if p['sec'] == 'ABS' else sum(1 for k in sec_no if k != 'ABSTRACT') + 1
        for j, s in enumerate(split_sents(text), 1):
            sents.append(dict(sec=sec_no[major], type=p['sec'], title=p['title'], para=f'P{pnum:03d}', sip=j, text=s, page=p['page'] + 1))
    cnt, order = Counter(), 0
    for s in sents:
        cnt[s['sec']] += 1; order += 1
        s['id'] = f"{s['sec']}-{cnt[s['sec']]:03d}"; s['order'] = order
        s['prose'] = not NONPROSE.search(s['text'])
        s['cites'] = bool(re.search(r'\[(\d[\d,\s–−-]*)\]', s['text']))   # 분석 도구 rvtool과 같은 정의
    cited = set()
    for s in sents:
        for g in re.findall(r'\[(\d[\d,–a-z]*)\]', s['text']):
            for part in re.sub(r'(?<=\d)[a-z]', '', g).split(','):
                r_ = re.fullmatch(r'(\d+)–(\d+)', part)
                if r_: cited |= set(range(int(r_.group(1)), int(r_.group(2)) + 1))
                elif part.isdigit(): cited.add(int(part))
    sha = hashlib.sha256(open(pdf_path, 'rb').read()).hexdigest()
    term = re.compile(r'[.!?:]["”)]?(\s*\[[\d,–]+\])?$')
    cid = Counter(m for s_ in sents for m in re.findall(r'\(cid:\d+\)', s_['text']))
    for k_, v_ in cid.items(): review.append(dict(type='대응 없는 글리프', where=doc_id, original=k_, rendered='', note=f'{v_}회: 원래 기호를 확인해야 함'))
    stats = dict(document_id=doc_id, source_type='pdf', extractor=VERSION, sentences=len(sents), paragraphs=pnum,
                 citing_sentences=sum(s['cites'] for s in sents), nonprose=sum(not s['prose'] for s in sents),
                 equations_removed=len(equations), margin_chars_removed=removed_margin, refs_in_list=max_ref,
                 cited_in_list=len(cited & set(range(1, max_ref + 1))), cited_outside_list=sorted(cited - set(range(1, max_ref + 1))),
                 never_cited=sorted(set(range(1, max_ref + 1)) - cited),
                 lowercase_starts=[s['id'] for s in sents if re.match(r'[a-z]', s['text'])],
                 no_terminal_punct=[s['id'] for s in sents if s['prose'] and not term.search(s['text'])],
                 by_section=dict(Counter(s['type'] for s in sents)), review_items=len(review),
                 leaks=[s['id'] for s in sents if re.search(r'Downloaded|NATL UNIV|UNIV user|\buser on \d{1,2} [A-Z][a-z]+ \d{4}|pubs\.acs|American Chemical Society|dx\.doi', s['text'])],   # 여백 문구 "… by <기관> user on 21 October 2026"
                 body_size=body_size, main_font=main_font, sha256=sha)
    with open(os.path.join(out_dir, f'{doc_id}_input.txt'), 'w', encoding='utf-8') as f:
        f.write(f'# document_id: {doc_id}\n# source_type: pdf\n# source_file: {os.path.basename(pdf_path)}\n# source_sha256: {sha}\n'
                f'# extractor: {VERSION}\n# needs_review: true\n# 총 문장 수: {len(sents)}\n# 총 문단 수: {pnum}\n'
                f'# 인용 표지 문장 수: {stats["citing_sentences"]}\n# 비문장(prose=false) 문장 수: {stats["nonprose"]}\n'
                f'# 여백 문구 제거(회전 글자, 기관명 포함): {removed_margin}자\n')
        for s in sents: f.write(f"{s['id']}\t{s['text']}\n")
    with open(os.path.join(out_dir, f'{doc_id}_structure.tsv'), 'w', encoding='utf-8', newline='') as f:
        w = csv.writer(f, delimiter='\t', lineterminator='\n')
        w.writerow(['document_id', 'sentence_id', 'order', 'section_type', 'section_label', 'section_title', 'paragraph_id', 'sentence_in_paragraph', 'word_count', 'prose', 'page'])
        for s in sents: w.writerow([doc_id, s['id'], s['order'], s['type'], str(s['sec']), s['title'], s['para'], s['sip'], len(s['text'].split()), str(s['prose']).lower(), s['page']])
    with open(os.path.join(out_dir, f'{doc_id}_review.csv'), 'w', encoding='utf-8-sig', newline='') as f:
        w = csv.DictWriter(f, fieldnames=['type', 'where', 'original', 'rendered', 'note']); w.writeheader(); w.writerows(review)
    json.dump(dict(stats=stats, equations=equations), open(os.path.join(out_dir, f'{doc_id}_report.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    # 검증 그림(render_layout.py)용: 줄마다 쪽·위치·종류·절, 초록 영역. 세기에는 쓰지 않는다
    layout = dict(document_id=doc_id, extractor=VERSION, body_size=body_size, pages=[[p.width, p.height] for p, _ in P], abstract_box=abs_box,
                  lines=[dict(page=l['page'], top=round(l['top'], 1), x0=round(l['x0'], 1), x1=round(l['x1'], 1), kind=l['kind'],
                              sec=l.get('sec', 'END' if id(l) in body_ids else 'TOP'), used=l.get('used', False), head=l['head']) for l in lines_all])
    json.dump(layout, open(os.path.join(out_dir, f'{doc_id}_layout.json'), 'w', encoding='utf-8'), ensure_ascii=False)
    return stats

if __name__ == '__main__':
    st = main(*sys.argv[1:4]); print(json.dumps({k: (v if not isinstance(v, list) else len(v)) for k, v in st.items()}, ensure_ascii=False))
