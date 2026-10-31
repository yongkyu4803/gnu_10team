"""PDF -> 섹션별 문단 + 인용 표지 (corpus/<id>.json).
2단 읽기 순서 복원, 캡션·표·머리말 제거. 번호식 인용 위첨자(ACS 등)는 ⟦c:1−4⟧ 표지로 남긴다.
참고문헌 번호의 최댓값(n_refs)을 함께 저장해, 그보다 큰 번호의 위첨자는 인용으로 보지 않는다.
섹션: INTRO / M(실험·계산) / RD(결과·논의) / CONCL
"""
import re, json, sys, os, glob, unicodedata
from collections import Counter, defaultdict
import pymupdf

HEAD = [
    (r'INTRODUCTION', 'INTRO'),
    (r'RESULTS AND DISCUSSION', 'RD'),
    (r'RESULTS', 'RD'),
    (r'DISCUSSION', 'RD'),
    (r'CONCLUSIONS?|SUMMARY AND CONCLUSIONS?|CONCLUDING REMARKS|REMARKS AND CONCLUSIONS?|CONCLUSIONS? AND (?:OUTLOOK|REMARKS|PERSPECTIVES?)', 'CONCL'),
    (r'EXPERIMENTAL SECTION|EXPERIMENTAL|EXPERIMENTAL PROCEDURES?|MATERIALS AND METHODS', 'M'),
    (r'COMPUTATIONAL DETAILS|COMPUTATIONAL METHODS?|THEORETICAL METHODS?', 'M'),
    (r'ASSOCIATED CONTENT|SUPPORTING INFORMATION', 'BACK'),
    (r'AUTHOR INFORMATION', 'BACK'),
    (r'ACKNOWLEDGMENTS?|ACKNOWLEDGEMENTS?', 'BACK'),
    (r'REFERENCES( AND NOTES)?|NOTES AND REFERENCES', 'REFS'),
]
RUNNING = re.compile(r'^\S+( \S)? et al\.$|^(Article|Featured Article|Note|JOC\s*Article|pubs\.acs\.org/joc|The Journal of Organic Chemistry)$|dx\.doi\.org|^©|^r \d{4} American|J\. Org\. Chem\.|Inorganic Chemistry,? Vol\.|^\*\s*To whom correspondence|^DOI:|^Received[: ]|^Published[: ]|^Revised|^\d{1,5}$')
REFLINE = re.compile(r'^\(\d{1,3}\)\s|\b(?:19|20)\d{2},\s*\d+,\s*\d+|;\s*[A-Z][a-z]+(?:-[A-Z][a-z]+)?,\s*[A-Z]\.')
CAP = re.compile(r'^(S ?CHEME|F ?IGURE|T ?ABLE|C ?HART)\s*(\d+)\.?', re.I)


def pdf_rows(pdf):
    doc = pymupdf.open(pdf)
    rows = []
    bid = 0
    for pi, page in enumerate(doc):
        W = page.rect.width; mid = W / 2
        blocks = [b for b in page.get_text('dict')['blocks'] if b.get('type') == 0]

        def geo(b):
            x0, y0, x1, _ = b['bbox']
            k = 'F' if (x0 < mid - 20 and x1 > mid + 20) else ('L' if x1 <= mid + 20 else 'R')
            return k, y0
        info = sorted([(geo(b), b) for b in blocks], key=lambda t: t[0][1])
        bands = []
        for (k, y), b in info:
            g = 'F' if k == 'F' else 'C'
            if not bands or bands[-1][0] != g: bands.append([g, []])
            bands[-1][1].append((k, b))
        ordered = []
        for g, items in bands:
            if g == 'F': ordered += [b for _, b in items]
            else: ordered += [b for k, b in items if k == 'L'] + [b for k, b in items if k == 'R']
        for block in ordered:
            bid += 1
            bx0, _, bx1, _ = block['bbox']
            for line in block['lines']:
                # 헤딩 앞 ■ 같은 장식 글리프(큰 글꼴)는 줄 높이 계산을 왜곡하므로 제외
                # (인용 범위의 '−'처럼 기호 하나뿐인 span은 남겨야 하므로 장식 기호·사용자 정의 글리프만 뺀다)
                spans = [s for s in line['spans'] if s['text'].strip() and s['size'] < 20
                         and not re.fullmatch(r'[■□▪●◆-�]+', s['text'].strip())]
                if not spans: continue
                H = max(s['size'] for s in spans)
                base = max(s['origin'][1] for s in spans)
                txt = ''; prev_x1 = None
                for s in spans:
                    t = s['text']
                    if s['size'] < 4.0: continue
                    if (s['size'] < 0.8 * H and s['origin'][1] < base - 1.0):
                        txt = txt.rstrip() + '^{' + t.strip() + '}'
                        prev_x1 = s['bbox'][2]
                        continue
                    # 글꼴이 바뀌는 단어 경계에서 공백이 span에 빠지는 경우 bbox 간격으로 복원
                    if prev_x1 is not None and s['bbox'][0] - prev_x1 > 0.15 * s['size'] and not txt.endswith(' ') and not t.startswith(' '):
                        txt += ' '
                    txt += t
                    prev_x1 = s['bbox'][2]
                txt = re.sub(r'\s+', ' ', txt).strip()
                if not txt or 'Downloaded' in txt or 'article-pdf' in txt: continue
                if re.fullmatch(r'\d{1,5}', txt) and H < 9: continue
                rows.append(dict(page=pi + 1, bid=bid, H=H, x0=line['bbox'][0], x1=line['bbox'][2], bx0=bx0, bx1=bx1, t=txt))
    return rows


def heading(text):
    t = re.sub(r'^[^\w]*(\d+\.\s*)?', '', text).strip()     # ■, ’ 등 헤딩 앞 장식 글리프 제거
    for pat, lab in HEAD:
        if re.fullmatch(pat, t.upper()) and len(t) < 45:
            return lab, t
    return None


def dehyph(lines):
    out = ''
    for l in lines:
        if not out: out = l; continue
        if out.endswith('-') and len(out) > 1 and out[-2].isalpha() and l[:1].islower():
            out = out[:-1] + l
        else:
            out = out + ' ' + l
    return out


# 1−4, 3a,b, 7a,9 는 인용. 2−, 3− 처럼 뒤에 숫자가 없는 하이픈은 이온 전하([Fe(CN)5NO]2−)이므로 제외
CITE_BODY = re.compile(r'^\d{1,3}[a-h]?(?:\s*,\s*(?:\d{1,3}[a-h]?|[a-h])|\s*[−–-]\s*\d{1,3}[a-h]?)*$')
UNIT = re.compile(r'(sp|cm|mm|nm|μm|s|h|K|M|mol|L|dm|m|g|kg|kJ|kcal|eV|Hz|MHz|[A-Z][a-z]?\d*)')


def mark_citations(p, nref):
    """위첨자 중 인용 번호는 ⟦c:본문⟧, 나머지(단위 지수·동위원소·전하)는 본문에 붙인다."""
    p = re.sub(r'\}\^\{', '', p)          # '1','−','4'처럼 span이 나뉜 위첨자를 하나로 합침
    out = []; pos = 0
    for m in re.finditer(r'\^\{([^}]*)\}', p):
        out.append(p[pos:m.start()]); pos = m.end()
        body = m.group(1).strip()
        pre = p[:m.start()]
        nxt = p[m.end():m.end() + 1]
        w = re.search(r'(\S+)$', pre)
        ok = bool(CITE_BODY.match(body)) and pre and not pre.endswith(' ') and w \
            and not UNIT.fullmatch(w.group(1)) and not re.search(r'\d$', w.group(1)) \
            and not (nxt and nxt.isalpha())                       # ^{13}C 같은 접두 위첨자
        if ok and nref:
            ok = all(int(x) <= nref for x in re.findall(r'\d+', body))
        out.append(f'⟦c:{body}⟧' if ok else body)
    out.append(p[pos:])
    p = unicodedata.normalize('NFKC', ''.join(out))
    p = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]', ' ', p)       # 수식 글리프에서 나온 제어 문자
    return re.sub(r'\s{2,}', ' ', p).strip()


def find_nref(rows):
    """참고문헌 목록(말미 목록 또는 쪽 하단 각주)의 '(n) ' 번호 최댓값"""
    body = Counter(round(r['H'], 1) for r in rows if len(r['t']) > 40).most_common(1)[0][0]
    start = next((i for i, r in enumerate(rows) if heading(r['t']) and heading(r['t'])[0] == 'REFS'), None)
    nums = []
    for i, r in enumerate(rows):
        m = re.match(r'^\((\d{1,3})\)\s', r['t'])
        if m and ((start is not None and i > start) or r['H'] < body - 0.4):
            nums.append(int(m.group(1)))
    return max(nums) if nums else None


def process(pdf):
    pid = os.path.basename(pdf)[:-4]
    rows = pdf_rows(pdf)
    if not any(len(r['t']) > 40 for r in rows):
        raise ValueError('분석할 텍스트가 부족합니다. 스캔 PDF는 OCR이 필요합니다.')
    nref = find_nref(rows)
    raw_all = '\n'.join(r['t'] for r in rows)
    m = re.search(r'(?:J\. Org\. Chem\.|Inorg\. Chem\.),? (?:Vol\. \d+, No\. \d+, )?(\d{4})', raw_all)
    year = int(m.group(1)) if m else None
    body_mode = Counter(round(r['H'], 1) for r in rows if len(r['t']) > 40).most_common(1)[0][0]
    cur = 'FRONT'; heads = []; secrows = defaultdict(list)
    for r in rows:
        t = r['t']
        if RUNNING.search(t): continue
        if re.match(r'^(Acknowledg(e)?ments?\.|Supporting Information Available:)', t):
            cur = 'BACK'; heads.append('BACK'); continue
        h = heading(t)
        if h and r['H'] >= 8:
            cur = h[0]; heads.append(h[0]); continue
        secrows[cur].append(r)
    sections = {}
    for lab, rs in secrows.items():
        if lab in ('FRONT', 'BACK', 'REFS'): continue
        # 본문 글자 크기: 참고문헌 항목처럼 보이는 줄은 빼고 센다 (2010년 서식은 각주 참고문헌이 본문 사이에 많이 끼어 있음)
        sizes = Counter(round(r['H'], 1) for r in rs if len(r['t']) > 40 and not REFLINE.search(r['t']))
        mode = sizes.most_common(1)[0][0] if sizes else body_mode
        paras = []; buf = []; incap = False
        for r in rs:
            t = r['t']
            if CAP.match(t): incap = True
            if r['H'] < mode - 0.4: continue          # 캡션·표·그림 내부 텍스트
            if incap and not CAP.match(t): incap = False
            if incap: continue
            colw = r['bx1'] - r['bx0']
            if r['x0'] - r['bx0'] > 5 and colw > 150 and buf:
                paras.append(dehyph(buf)); buf = []
            buf.append(t)
        if buf: paras.append(dehyph(buf))
        # 줄마다 들여쓰기로 오인해 문장 중간에서 끊긴 문단(2010년 서식 등)은 다음 문단과 잇는다
        merged = []
        for p in paras:
            if merged and not re.search(r'[.!?:]\s*(\^\{[^}]*\}\s*)*$', merged[-1]):
                merged[-1] = dehyph([merged[-1], p])
            else:
                merged.append(p)
        paras = [mark_citations(p, nref) for p in merged]
        sections.setdefault(lab, []).extend(p for p in paras if len(p.split()) >= 4)
    return dict(id=pid, year=year, headings=heads, n_refs=nref, sections=sections)


if __name__ == '__main__':
    pdfdir, outdir = sys.argv[1], sys.argv[2]
    os.makedirs(outdir, exist_ok=True)
    for p in sorted(glob.glob(os.path.join(pdfdir, '*.pdf'))):
        d = process(p)
        json.dump(d, open(os.path.join(outdir, d['id'] + '.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
        wc = {k: sum(len(x.split()) for x in v) for k, v in d['sections'].items()}
        nc = {k: sum(x.count('⟦c:') for x in v) for k, v in d['sections'].items()}
        print(d['id'], d['year'], 'refs', d['n_refs'], '| 단어', wc, '| 인용 표지', nc)
