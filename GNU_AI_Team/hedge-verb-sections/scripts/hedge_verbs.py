"""섹션별 헷지 어휘동사 분석.

  build : corpus/*.json -> spaCy로 lexical VERB(AUX 제외) 추출·원형화 -> 후보 대조
          -> 앞·뒤 문장 맥락 + 자동 예비판정 -> 엑셀(판정작업지 + 통계)
  stats : 엑셀 '판정작업지'의 연구자판정(Hedge/N/U)을 읽어 통계 시트만 다시 계산
          (연구자판정이 빈 칸이면 자동 예비판정을 사용하고, 미검토 건수를 표시)

사용:
  python hedge_verbs.py build <corpus_dir> <out.xlsx> [review.json]
  python hedge_verbs.py dump  <out.xlsx> <candidates.txt>   (Claude 검토용 후보 목록)
  python hedge_verbs.py stats <out.xlsx>
"""
import sys, os, re, json, glob, statistics
from collections import Counter, defaultdict
from openpyxl import Workbook, load_workbook
from openpyxl.styles import Font, PatternFill, Alignment
from openpyxl.worksheet.datavalidation import DataValidation
from openpyxl.utils import get_column_letter

HEDGE_VERB_CANDIDATES = {
    # 현재 자료에서 발견된 후보
    "appear", "assume", "indicate", "propose", "seem", "speculate", "suggest", "tend",
    # 추가로 검토할 후보
    "argue", "believe", "claim", "conclude", "consider", "estimate", "expect", "hypothesize",
    "imply", "infer", "interpret", "posit", "postulate", "predict", "presume", "suppose", "think",
}
SEC_ORDER = ['INTRO', 'M', 'RD', 'CONCL']
SEC_NAME = {'INTRO': '서론', 'M': '방법', 'RD': '결과·논의', 'CONCL': '결론', 'ALL': '전체'}
LABELS = ('Hedge', 'N', 'U')
MODALS = {'may', 'might', 'could', 'would', 'should', 'can'}
REVIEW_SHEET = '판정작업지'
SIZE_SHEET = '섹션크기'


# ---------------------------------------------------------------- 자동 예비판정
def that_clause(tok):
    """동사 뒤에 that절/명제 보문(ccomp)이 오는가"""
    if any(c.dep_ == 'ccomp' for c in tok.children): return True
    nxt = [t.lower_ for t in tok.doc[tok.i + 1: tok.i + 4]]
    return 'that' in nxt


def to_inf(tok):
    """seem/appear/tend/be expected 뒤 to부정사"""
    if any(c.dep_ == 'xcomp' for c in tok.children): return True
    nxt = [t.lower_ for t in tok.doc[tok.i + 1: tok.i + 3]]
    return 'to' in nxt


def passive(tok):
    return any(c.dep_ in ('auxpass', 'nsubjpass') for c in tok.children)


def modal(tok):
    return any(c.dep_ == 'aux' and c.lower_ in MODALS for c in tok.children)


def prejudge(tok):
    """(판정, 근거) — 연구자 최종 판정 전의 예비 판정"""
    lem = tok.lemma_.lower()
    sent = tok.sent.text
    after = tok.doc[tok.i + 1: tok.i + 6].text.lower()
    before = tok.doc[max(tok.sent.start, tok.i - 3): tok.i].text.lower()
    tc, ti, pv, md = that_clause(tok), to_inf(tok), passive(tok), modal(tok)

    if lem in ('indicate', 'suggest', 'imply'):
        if re.search(r'\b(figure|fig\.|table|scheme|chart|arrow|asterisk|bold|red|blue)\b', after) or re.search(r'\bas\b', before) and lem == 'indicate':
            return 'N', '도식·위치 지시(as indicated / indicated in Figure)'
        if lem == 'suggest' and re.match(r'\s*(using|the use|to\b)', after):
            return 'N', '제안·권고 의미'
        if tc or md:
            return 'Hedge', '증거 기반 추론(that절/양태 조동사)'
        return 'U', '목적어가 명사구 — 추론인지 지시인지 확인'
    if lem in ('appear', 'seem'):
        if ti or tc or re.search(r'\bit\b', before):
            return 'Hedge', 'seem/appear to·that (인식적)'
        if lem == 'appear' and re.search(r'\b(at|in|around|near)\b', after):
            return 'N', '“나타나다(관찰)” 의미'
        return 'U', '보어 구조 확인 필요'
    if lem == 'tend':
        return ('Hedge', 'tend to') if ti else ('U', 'to부정사 없음')
    if lem in ('speculate', 'hypothesize', 'postulate', 'posit', 'presume', 'suppose', 'infer'):
        return 'Hedge', '추정 동사'
    if lem in ('believe', 'think'):
        if tc or ti or pv: return 'Hedge', '인식 동사 + that절/수동'
        return 'U', '인식 의미인지 확인'
    if lem == 'assume':
        if re.match(r'\s*(a|an|the)\s+\w*\s*(conformation|geometry|structure|shape|form|configuration)', after):
            return 'N', '“(형태를) 취하다” 의미'
        if tc or ti or md: return 'Hedge', '가정 + that절/to be'
        return 'U', '방법상 가정인지 확인'
    if lem == 'propose':
        if re.search(r'\bby\b', after) or re.search(r'\bhas been|have been|was\b', before) and not md:
            return 'U', '타 연구 보고 가능성'
        if tc or md or tok.dep_ == 'amod' or re.match(r'\s*(mechanism|pathway|structure|model)', after):
            return 'Hedge', '메커니즘·구조 제안'
        return 'U', '제안 대상 확인'
    if lem == 'expect':
        if re.search(r'\bas\b', before) or re.search(r'\bthan\b', before):
            return 'N', 'as/than expected (기대 확인·비교)'
        if ti or tc or md: return 'Hedge', '예상 + to/that절'
        return 'U', '예상 의미 확인'
    if lem == 'predict':
        if md or tc: return 'Hedge', '예측 + that절/양태'
        return 'U', '계산상 예측(보고)인지 확인'
    if lem == 'estimate':
        if md: return 'Hedge', '양태 조동사 + 추정'
        return 'U', '수치 추정(방법 기술)인지 확인'
    if lem == 'consider':
        if ti or re.match(r'\s*(as|to be)\b', after) or md:
            return 'Hedge', 'be considered (to be/as)'
        return 'N', '“고려하다·검토하다” 의미'
    if lem == 'interpret':
        if md or re.match(r'\s*as\b', after): return 'Hedge', 'interpret as / 양태'
        return 'U', '해석 행위 기술인지 확인'
    if lem == 'conclude':
        if md: return 'U', '양태 + 결론 — 확인'
        return 'N', '결론 진술(헷지 아님)'
    if lem in ('argue', 'claim'):
        return 'U', '보고/주장 — 저자 자신의 주장인지 확인'
    return 'U', ''


# ---------------------------------------------------------------- build
def paper_ids(docs):
    docs.sort(key=lambda d: (d['year'] or 0, d['id']))
    return {d['id']: f'P{i + 1:02d}' for i, d in enumerate(docs)}


def is_word(t):
    return not (t.is_punct or t.is_space) and any(ch.isalnum() for ch in t.text)


def build(corpus_dir, out_xlsx, review_path=None):
    import spacy
    nlp = spacy.load('en_core_web_sm')
    docs = [json.load(open(f, encoding='utf-8')) for f in sorted(glob.glob(os.path.join(corpus_dir, '*.json')))]
    pid = paper_ids(docs)
    sizes = []; rows = []
    for d in docs:
        for sec in SEC_ORDER:
            paras = d['sections'].get(sec, [])
            sents = []
            for doc in nlp.pipe(paras):
                sents += list(doc.sents)
            n_words = sum(1 for s in sents for t in s if is_word(t))
            verbs = [t for s in sents for t in s if t.pos_ == 'VERB' and t.lemma_.isalpha() and len(t.lemma_) > 1]
            sizes.append(dict(pid=pid[d['id']], file=d['id'], sec=sec, words=n_words, verbs=len(verbs),
                              verb_lemmas=Counter(t.lemma_.lower() for t in verbs)))
            for si, s in enumerate(sents):
                for t in s:
                    lem = t.lemma_.lower()
                    if t.pos_ != 'VERB' or lem not in HEDGE_VERB_CANDIDATES: continue
                    lab, why = prejudge(t)
                    marked = s.text[: t.idx - s.start_char] + '【' + t.text + '】' + s.text[t.idx - s.start_char + len(t.text):]
                    rows.append(dict(pid=pid[d['id']], file=d['id'], sec=sec, sent_no=si + 1, form=t.text, lemma=lem,
                                     prev=sents[si - 1].text if si > 0 else '', sent=marked,
                                     next=sents[si + 1].text if si + 1 < len(sents) else '',
                                     auto=lab, why=why))
        print(pid[d['id']], d['id'], {s['sec']: (s['words'], s['verbs']) for s in sizes if s['file'] == d['id']})
    write_workbook(out_xlsx, rows, sizes, review_path)
    stats(out_xlsx)


HDR_FONT = Font(bold=True, color='FFFFFF')
HDR_FILL = PatternFill('solid', fgColor='305496')


def header(ws, cols, widths=None):
    ws.append(cols)
    for i, c in enumerate(cols, 1):
        cell = ws.cell(row=1, column=i)
        cell.font = HDR_FONT; cell.fill = HDR_FILL
        cell.alignment = Alignment(wrap_text=True, vertical='center')
        if widths: ws.column_dimensions[get_column_letter(i)].width = widths[i - 1]
    ws.freeze_panes = 'A2'


def write_workbook(path, rows, sizes, review_path=None):
    wb = Workbook()
    ws = wb.active; ws.title = '안내'
    for line in README: ws.append([line])
    ws.column_dimensions['A'].width = 140

    ws = wb.create_sheet(REVIEW_SHEET)
    cols = ['ID', '논문', '섹션', '문장번호', '형태', '원형', '앞 문장', '후보 문장(【동사】)', '뒤 문장',
            '자동 예비판정', '판정 근거', 'Claude 검토판정', 'Claude 메모', '연구자판정 (Hedge/N/U)', '메모']
    header(ws, cols, [5, 6, 5, 9, 11, 11, 45, 70, 45, 9, 28, 10, 30, 14, 25])
    order = {s: i for i, s in enumerate(SEC_ORDER)}
    rows.sort(key=lambda r: (r['pid'], order[r['sec']], r['sent_no']))
    review = json.load(open(review_path, encoding='utf-8')) if review_path and os.path.exists(review_path) else {}
    for i, r in enumerate(rows, 1):
        lem, lab, memo = review.get(str(i), [r['lemma'], '', ''])
        if lem != r['lemma']:       # 후보 목록이 바뀌어 ID가 밀린 경우 검토판정을 붙이지 않음
            print(f'경고: 검토판정 ID {i} 원형 불일치({lem} ≠ {r["lemma"]}) — 건너뜀'); lab, memo = '', ''
        ws.append([i, r['pid'], SEC_NAME[r['sec']], r['sent_no'], r['form'], r['lemma'], r['prev'], r['sent'],
                   r['next'], r['auto'], r['why'], lab, memo, '', ''])
    for row in ws.iter_rows(min_row=2):
        for c in row[6:9]: c.alignment = Alignment(wrap_text=True, vertical='top')
    dv = DataValidation(type='list', formula1='"Hedge,N,U"', allow_blank=True)
    ws.add_data_validation(dv); dv.add(f'N2:N{max(2, len(rows) + 1)}')
    ws.auto_filter.ref = ws.dimensions

    ws = wb.create_sheet(SIZE_SHEET)
    header(ws, ['ID', '논문', '섹션', '단어 수', 'lexical verb 수'], [6, 12, 10, 10, 14])
    for s in sizes:
        ws.append([s['pid'], s['file'], SEC_NAME[s['sec']], s['words'], s['verbs']])
    ws = wb.create_sheet('동사분포(전체)')
    header(ws, ['ID', '섹션', '원형', '빈도'], [6, 10, 16, 8])
    for s in sizes:
        for lem, n in s['verb_lemmas'].most_common():
            ws.append([s['pid'], SEC_NAME[s['sec']], lem, n])
    wb.save(path)


# ---------------------------------------------------------------- stats
def summarize(vals):
    v = [x for x in vals if x is not None]
    if not v: return dict(mean=None, sd=None, median=None, lo=None, hi=None)
    return dict(mean=statistics.mean(v), sd=statistics.stdev(v) if len(v) > 1 else 0.0,
                median=statistics.median(v), lo=min(v), hi=max(v))


def stats(path):
    wb = load_workbook(path)
    name2sec = {v: k for k, v in SEC_NAME.items()}
    # 섹션 크기
    size = {}
    for r in wb[SIZE_SHEET].iter_rows(min_row=2, values_only=True):
        if r[0]: size[(r[0], name2sec[r[2]])] = dict(words=r[3], verbs=r[4])
    papers = sorted({p for p, _ in size})
    # 판정
    hedge = defaultdict(Counter)        # (pid, sec) -> lemma -> n
    label_n = Counter(); source = Counter(); bad = []; by_lemma = defaultdict(Counter)
    for r in wb[REVIEW_SHEET].iter_rows(min_row=2, values_only=True):
        if r[0] is None: continue
        # 우선순위: 연구자판정 > Claude 검토판정 > 자동 예비판정
        for col, src in ((13, '연구자'), (11, 'Claude'), (9, '자동')):
            final = (r[col] or '').strip() if isinstance(r[col], str) else r[col]
            if final: source[src] += 1; break
        if final not in LABELS: bad.append((r[0], final)); continue
        label_n[final] += 1
        by_lemma[r[5]][final] += 1
        if final == 'Hedge':
            hedge[(r[1], name2sec[r[2]])][r[5]] += 1
    if bad: print('경고: 알 수 없는 판정값', bad[:10])

    for name in ['논문×섹션', '섹션요약', '동사×섹션', '논문×동사', '후보동사 점검']:
        if name in wb.sheetnames: del wb[name]

    def cell(p, sec):
        if sec == 'ALL':
            w = sum(size[(p, s)]['words'] for s in SEC_ORDER); v = sum(size[(p, s)]['verbs'] for s in SEC_ORDER)
            h = sum(sum(hedge[(p, s)].values()) for s in SEC_ORDER)
        else:
            w, v = size[(p, sec)]['words'], size[(p, sec)]['verbs']; h = sum(hedge[(p, sec)].values())
        return dict(n=h if w else None, words=w, verbs=v, p10k=h / w * 10000 if w else None, p100v=h / v * 100 if v else None)

    secs = SEC_ORDER + ['ALL']
    # 1) 논문×섹션
    ws = wb.create_sheet('논문×섹션')
    header(ws, ['ID', '섹션', '단어 수', 'lexical verb 수', '헷지 동사(원빈도)', '10,000단어당', 'lexical verb 100개당', '주의'],
           [6, 10, 10, 14, 15, 13, 18, 30])
    for p in papers:
        for sec in secs:
            c = cell(p, sec)
            note = '본문 없음 — 추출 누락 또는 해당 섹션 없음' if not c['words'] else ('300단어 미만 — 비율 불안정' if c['words'] < 300 else '')
            ws.append([p, SEC_NAME[sec], c['words'], c['verbs'], c['n'], rnd(c['p10k']), rnd(c['p100v']), note])
    # 2) 섹션요약 (논문 간 평균·범위)
    ws = wb.create_sheet('섹션요약')
    header(ws, ['섹션', '지표', '평균', '표준편차', '중앙값', '최소', '최대', '범위(최소–최대)', '출현 논문 수', '합산 비율(풀링)'],
           [10, 24, 9, 9, 9, 9, 9, 16, 12, 14])
    for sec in secs:
        cs = [cell(p, sec) for p in papers]
        k = sum(1 for c in cs if (c['n'] or 0) > 0)
        tw, tv, tn = sum(c['words'] for c in cs), sum(c['verbs'] for c in cs), sum(c['n'] or 0 for c in cs)
        for key, lab, pooled in [('n', '원빈도(토큰)', tn), ('p10k', '10,000단어당', tn / tw * 10000 if tw else None),
                                 ('p100v', 'lexical verb 100개당', tn / tv * 100 if tv else None)]:
            s = summarize([c[key] for c in cs])
            ws.append([SEC_NAME[sec], lab, rnd(s['mean']), rnd(s['sd']), rnd(s['median']), rnd(s['lo']), rnd(s['hi']),
                       f"{fmt(s['lo'])}–{fmt(s['hi'])}", f"{k}/{sum(c['words'] > 0 for c in cs)}", rnd(pooled)])
    ws.append([])
    ws.append([f'판정 집계: Hedge {label_n["Hedge"]}, N {label_n["N"]}, U {label_n["U"]} (U는 헷지 수에서 제외) / '
               f'판정 출처: 연구자 {source["연구자"]}, Claude 검토 {source["Claude"]}, 자동 {source["자동"]}건'])
    ws.append([f'평균·표준편차·범위는 논문 {len(papers)}편의 값(논문당 1개)을 기준으로 함. 합산 비율은 전체 토큰 ÷ 전체 단어(또는 동사).'])
    # 3) 동사×섹션 (출현 편수, 한 논문 지배도)
    ws = wb.create_sheet('동사×섹션')
    header(ws, ['원형', '섹션', '토큰 수', '출현 논문 수', '논문별 토큰', '최다 논문 비중(%)', '10,000단어당(풀링)', '지배 경고'],
           [12, 10, 9, 12, 40, 15, 16, 30])
    lemmas = sorted({l for c in hedge.values() for l in c}, key=lambda l: -sum(c[l] for c in hedge.values()))
    for lem in lemmas:
        for sec in secs:
            per = {p: (sum(hedge[(p, s)][lem] for s in SEC_ORDER) if sec == 'ALL' else hedge[(p, sec)][lem]) for p in papers}
            tot = sum(per.values())
            if tot == 0: continue
            tw = sum(cell(p, sec)['words'] for p in papers)
            top = max(per.values())
            k = sum(1 for v in per.values() if v)
            warn = '한 논문이 과반 차지' if top / tot > 0.5 and tot >= 3 else ('1편에서만 출현' if k == 1 else '')
            ws.append([lem, SEC_NAME[sec], tot, f'{k}/{len(papers)}', ', '.join(f'{p}:{v}' for p, v in per.items() if v),
                       round(top / tot * 100), rnd(tot / tw * 10000), warn])
    # 4) 논문×동사 행렬 (전체 섹션)
    ws = wb.create_sheet('논문×동사')
    header(ws, ['원형'] + papers + ['합계', '출현 논문 수'], [12] + [7] * len(papers) + [7, 12])
    for lem in lemmas:
        per = [sum(hedge[(p, s)][lem] for s in SEC_ORDER) for p in papers]
        ws.append([lem] + per + [sum(per), f'{sum(1 for v in per if v)}/{len(papers)}'])
    # 5) 후보 목록 전체 각각이 VERB로 몇 번 나왔고 어떻게 판정됐는지
    ws = wb.create_sheet('후보동사 점검')
    header(ws, ['원형', 'VERB 토큰', 'Hedge', 'N', 'U', 'Hedge 비율(%)'], [12, 10, 8, 8, 8, 12])
    for lem in sorted(HEDGE_VERB_CANDIDATES, key=lambda l: (-sum(by_lemma[l].values()), l)):
        c = by_lemma[lem]; tot = sum(c.values())
        ws.append([lem, tot, c['Hedge'], c['N'], c['U'], round(c['Hedge'] / tot * 100) if tot else None])
    wb.save(path)
    print(f'통계 갱신: {path}  (Hedge {label_n["Hedge"]}, N {label_n["N"]}, U {label_n["U"]}, 출처 {dict(source)})')


def dump(path, out_txt):
    """검토용: 판정작업지의 후보를 앞·뒤 문장과 함께 UTF-8 텍스트로 출력"""
    ws = load_workbook(path)[REVIEW_SHEET]
    with open(out_txt, 'w', encoding='utf-8') as f:
        for r in ws.iter_rows(min_row=2, values_only=True):
            if r[0] is None: continue
            f.write(f'#{r[0]} {r[1]} {r[2]} {r[5]} [자동 {r[9]}: {r[10]}]\n  앞: {r[6]}\n  ▶ {r[7]}\n  뒤: {r[8]}\n\n')
    print(f'후보 {ws.max_row - 1}건 → {out_txt}')


def rnd(x, d=2):
    return None if x is None else round(x, d)


def fmt(x):
    return '—' if x is None else f'{x:.2f}'


README = [
    '섹션별 헷지 어휘동사 분석 — 작업 안내',
    '',
    '절차: 논문 → spaCy(en_core_web_sm)로 lexical VERB 추출(AUX 제외) → 원형 통합(lemma) → 후보 목록 대조 → 후보 문장+앞·뒤 문장 출력 → 자동 예비판정 → 연구자 최종 판정(Hedge/N/U) → 섹션별·동사별 빈도',
    '섹션: 서론(INTRODUCTION), 방법(EXPERIMENTAL SECTION + COMPUTATIONAL DETAILS), 결과·논의(RESULTS AND DISCUSSION), 결론(CONCLUSION). 초록·참고문헌·사사·캡션·표는 제외.',
    '단어 수: spaCy 토큰 중 문장부호·공백을 뺀 토큰(숫자·화합물 번호 포함). lexical verb 수: POS=VERB(AUX 제외)이고 원형이 알파벳인 토큰.',
    '',
    '[연구자 판정 방법]',
    "1. '판정작업지' 시트의 N열 '연구자판정'에 Hedge / N / U 중 하나를 고릅니다(드롭다운).",
    '   통계에 쓰이는 판정의 우선순위: 연구자판정 > Claude 검토판정(L열, 후보 전부 앞·뒤 문장을 읽고 판정) > 자동 예비판정(J열). 연구자판정이 빈 칸이면 Claude 검토판정이 쓰입니다.',
    '   Hedge = 명제의 확실성을 낮추는 인식적 용법 / N = 헷지 아님(예: as indicated by TLC, signal appears at δ, estimated by DFT, as expected) / U = 판단 보류(헷지 수에서 제외)',
    '   Claude 검토 기준: indicate/suggest + that절·추론 명사구는 Hedge, 타 연구 귀속(Many authors suggest)과 부스터 공기(clearly indicates, strongly suggests)는 U.',
    "2. 저장한 뒤 다음을 실행하면 통계 시트(논문×섹션, 섹션요약, 동사×섹션, 논문×동사)만 다시 계산됩니다:",
    '   <venv의 python> <스킬 폴더>/scripts/hedge_verbs.py stats <이 엑셀 파일 경로>',
    '',
    '[지표]',
    '원빈도 = Hedge로 판정된 토큰 수 / 10,000단어당 = 원빈도 ÷ 단어 수 × 10,000 / 동사 100개당 = 원빈도 ÷ lexical verb 수 × 100',
    '섹션요약의 평균·표준편차·범위는 논문당 값 기준(거시 평균). 합산 비율은 전체 논문을 합친 값. 출현 논문 수 = 해당 섹션에서 Hedge가 1건 이상인 논문 수.',
    '동사×섹션의 최다 논문 비중 = 해당 동사 토큰 중 가장 많이 쓴 한 논문의 몫. 50%를 넘으면(토큰 3건 이상) 한 논문이 결과를 지배할 수 있다는 경고.',
]


if __name__ == '__main__':
    if sys.argv[1] == 'build': build(sys.argv[2], sys.argv[3], sys.argv[4] if len(sys.argv) > 4 else None)
    elif sys.argv[1] == 'dump': dump(sys.argv[2], sys.argv[3])
    elif sys.argv[1] == 'stats': stats(sys.argv[2])
