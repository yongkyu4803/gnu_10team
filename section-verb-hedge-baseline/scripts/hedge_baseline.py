"""
섹션별 기능 동사·헷지·비헷지·보고동사 기준선(Stage 1)
사용: python3 scripts/hedge_baseline.py <추출 폴더> <출력 폴더> [--include-abstract] [--model en_core_web_sm]

입력: extract_pdf.py가 만든 <id>_input.txt + <id>_structure.tsv (같은 폴더, 2~10편)
출력:
  per_paper.csv        논문 × 절 × 지표 값(개수, 단어 수, 1,000단어당)
  baseline.csv         절 × 지표 기준선(편수, 중간값, 최솟값, 최댓값)
  common_verbs.csv     절별 공통 동사(절반 이상 논문에 나온 동사, 중간값 순)
  evidence.csv         모든 개수의 근거(논문, 문장 ID, 범주, 표현, 문장)
  checks.json          처리 검사(Pass/Fail): 입력·절 구성·단어 수
원칙: 값은 이 스크립트가 세고, 해석은 사람이(또는 모델이) 근거 문장을 보고 한다.
      prose=false 문장(NMR 등)은 세지 않는다. 헷지·비헷지는 실험 절(MET)을 분모에서 뺀다.
"""
import sys, os, re, csv, json, glob, argparse, statistics, math
from collections import Counter, defaultdict
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
import rvtool as rv, engine_local as L

VERSION = "hedge-baseline-0.4.4"
# Hyland (2005) Metadiscourse 부록(pp. 218-223)의 Hedges·Boosters 항목을 따른다(references/hedge_lexicon.md 참고). 품사로 거른다.
HEDGE = {
    'modal': ({'may', 'might', 'could', 'would', 'should', 'ought'}, {'MD'}),
    'verb': ({'suggest', 'indicate', 'appear', 'seem', 'tend', 'assume', 'suspect', 'suppose', 'postulate', 'argue', 'claim', 'doubt', 'feel', 'guess'}, {'VERB'}),
    'adverb': ({'possibly', 'probably', 'presumably', 'perhaps', 'apparently', 'plausibly', 'likely', 'maybe', 'uncertainly', 'unclearly'}, {'ADV'}),
    'adjective': ({'possible', 'probable', 'likely', 'unlikely', 'plausible', 'presumable', 'doubtful', 'uncertain', 'unclear'}, {'ADJ'}),
}
BOOSTER = {
    'verb': ({'demonstrate', 'prove', 'establish', 'know', 'realize', 'think', 'believe'}, {'VERB'}),
    'adverb': ({'actually', 'certainly', 'clearly', 'conclusively', 'decidedly', 'definitely', 'doubtless', 'evidently', 'incontestably', 'incontrovertibly',
                'indeed', 'indisputably', 'obviously', 'really', 'surely', 'truly', 'undeniably', 'undisputedly', 'undoubtedly'}, {'ADV'}),
    'adjective': ({'clear', 'evident', 'obvious', 'definite', 'incontestable', 'incontrovertible', 'indisputable', 'undeniable', 'certain', 'sure', 'true'}, {'ADJ'}),
}
# 여러 낱말 표현(Hyland 부록 그대로). 문장 소문자에서 낱말 경계로 찾는다.
HEDGE_PHRASES = ['certain amount', 'certain extent', 'certain level', 'from my perspective', 'from our perspective', 'from this perspective', 'in general',
                 'in most cases', 'in most instances', 'in my opinion', 'in my view', 'in this view', 'in our opinion', 'in our view', 'on the whole', 'to my knowledge']
BOOSTER_PHRASES = ['beyond doubt', 'in fact', 'no doubt', 'of course', 'without doubt']
REVIEW_ONLY = {   # 헷지·비헷지에서 떼어 사람 확인 후보로만 둔다(세지만 합계에 넣지 않음)
    'can': ({'can'}, {'MD'}),
    'rounder': ({'about', 'approximately', 'roughly', 'nearly', 'almost', 'around', 'ca'}, {'ADV', 'ADP', 'X', 'NOUN', 'PROPN'}),
    'degree': ({'relatively', 'somewhat', 'partially', 'partly', 'generally', 'largely', 'essentially', 'mostly', 'mainly', 'slightly', 'fairly', 'quite', 'rather', 'broadly'}, {'ADV'}),   # 화학에서는 문자 그대로(partially blocking) 쓰이는 경우가 많다
    'frequency': ({'often', 'usually', 'sometimes', 'frequently', 'typically', 'always', 'never'}, {'ADV'}),   # Hyland는 헷지·강조로 세지만 화학에서는 관측 빈도인 경우가 많다
    'literal': ({'typical', 'apparent'}, {'ADJ'}),   # apparent rate constant, typical procedure 같은 용어
    'must': ({'must'}, {'MD'}),   # Hyland는 가능성의 must만 강조로 센다. 의무와 가르지 못한다
    'show_find': ({'show', 'find', 'estimate'}, {'VERB'}),   # Hyland는 show·find를 강조, estimate를 헷지로 세지만 화학에서는 결과 제시·연구 행위로 흔하다
    'team': ({'imply', 'propose', 'speculate', 'presume', 'confirm'}, {'VERB'}),   # Hyland 부록에 없는 팀 추가 낱말(v0.3.0까지 합계에 넣었음)
    'team_adv': ({'conceivably', 'unambiguously', 'unequivocally'}, {'ADV'}),
    'team_adj': ({'tentative', 'unambiguous'}, {'ADJ'}),
}
SECTIONS = ['ABS', 'INT', 'MET', 'RES', 'DIS', 'RD', 'CON']
HEDGE_SECTIONS = {'ABS', 'INT', 'RES', 'DIS', 'RD', 'CON'}   # MET 제외

def load(ex_dir):
    docs = []
    for txt in sorted(glob.glob(os.path.join(ex_dir, '*_input.txt'))):
        did = os.path.basename(txt)[:-len('_input.txt')]
        tsv = os.path.join(ex_dir, f'{did}_structure.tsv')
        D = rv.load_document(txt, tsv, did, document_version=open(txt, encoding='utf-8').read().split('# extractor: ')[1].split('\n')[0] if '# extractor: ' in open(txt, encoding='utf-8').read() else 'unversioned')
        prose = {r['sentence_id']: r.get('prose', 'true') == 'true' for r in csv.DictReader(open(tsv, encoding='utf-8'), delimiter='\t')}
        docs.append((D, prose))
    return docs

THAT_VERBS = {'suggest', 'indicate', 'assume', 'suspect', 'suppose', 'postulate', 'argue', 'claim', 'doubt', 'feel', 'guess',   # 헷지
              'know', 'realize', 'think', 'believe'}                                                                     # 강조(인지 동사)
RAISING = {'appear', 'seem', 'tend'}
CLAUSE_ADJ = {'certain', 'sure', 'true'}   # it is certain/true that, we are sure that 만(certain compounds, true value 제외)

def has_clause(tok):
    # that절·의문절 같은 명제 보어가 붙었는가(헷지로 쓰인 경우)
    return any(c.dep_ in ('ccomp',) for c in tok.children) or any(c.dep_ == 'mark' and c.lower_ == 'that' for c in tok.subtree if c.head == tok or c.head.head == tok)

def structural_ok(tok, lem):
    # 화학 논문의 문자 그대로 쓰임을 거른다: 'appears at 390 nm', 'indicated as ET', 'proposed structures', 'possible to distinguish'
    if lem in THAT_VERBS:
        if tok.dep_ == 'amod' or (tok.tag_ == 'VBN' and tok.dep_ in ('acl', 'amod')): return False
        return has_clause(tok)
    if lem in RAISING:
        return any(c.dep_ in ('xcomp', 'ccomp') for c in tok.children) or any(c.dep_ in ('expl', 'nsubj') and c.lower_ == 'it' for c in tok.children)
    if lem in CLAUSE_ADJ:
        return tok.dep_ != 'amod' and (has_clause(tok) or (tok.dep_ == 'acomp' and any(c.dep_ == 'ccomp' for c in tok.head.children)))
    if lem in ('possible', 'likely', 'unlikely', 'probable', 'plausible'):
        if tok.dep_ == 'amod': return True
        nxt = [c for c in tok.children if c.dep_ in ('xcomp',)]
        if nxt and lem == 'possible': return False                     # it is possible to + 동사(가능성 아닌 능력)
        return has_clause(tok) or any(c.dep_ in ('ccomp', 'xcomp') for c in tok.head.children if tok.dep_ == 'acomp')
    return True

# 원문 대조(CM·JOC 315건)에서 나온 오판 유형(hedge-baseline-0.4.2). 걸리면 합계에서 빼고 확인 후보(review:rule_*)로 남긴다
ABILITY_VERBS = {'detect', 'observe', 'obtain', 'isolate', 'recover', 'prepare', 'separate', 'identify', 'refine', 'position',
                 'resolve', 'locate', 'run', 'record', 'measure', 'purify', 'synthesize', 'grow', 'crystallize',
                 'repeat', 'exploit'}   # find는 뺀다("routes … could be found": 가능성). repeat·exploit은 IC 대조(0.4.4)
NEG_COULD_KEEP = {'rule', 'exclude', 'explain', 'account', 'attribute'}   # "could not be ruled out"은 추측이라 남긴다
DEONTIC_VERBS = {'avoid', 'prevent', 'minimize', 'eliminate'}           # "CO gas should be avoided"(의무)
LOCATION_PREPS = {'in', 'at', 'around', 'near', 'below', 'above'}       # "appears in the UV region", "appears at lower energy"
WEAKENERS = {'less', 'hardly', 'barely', 'scarcely', 'not', 'never'}   # 강조를 약하게 하거나 뒤집는 수식어
EVIDENCE_NOUNS = {'evidence', 'proof', 'indication', 'sign', 'demonstration', 'example', 'trend', 'picture'}   # "clear evidence"는 강조로 남긴다
DISCOURSE_VERBS = {'note', 'emphasize', 'mention', 'recall', 'stress', 'point', 'remember', 'bear'}
LITERAL_OBJ = {'establish': {'bond', 'class', 'interaction', 'contact', 'link', 'network', 'protocol'}, 'demonstrate': {'issue', 'problem'}}
LITERAL_ADJ_HEAD = {'possible': {'method', 'approach', 'route', 'alternative', 'bond', 'option', 'form'}}

def literal_reason(tok, lem):
    head = tok.head
    if lem == 'could' and head.lemma_.lower() in ABILITY_VERBS:
        return 'rule_could_ability'                 # "no emission could be detected", "could be recovered"(실제로 해낸 일)
    if lem == 'could' and any(c.dep_ == 'neg' for c in head.children) and head.lemma_.lower() not in NEG_COULD_KEEP:
        return 'rule_could_ability'                 # 0.4.4: "too much Zn2+ could not improve …"(실험 결과)
    if lem == 'should':
        if head.lemma_.lower() in DISCOURSE_VERBS: return 'rule_should_discourse'   # "It should be noted that"
        if any(c.dep_ == 'nsubj' and c.lower_ == 'we' for c in head.children): return 'rule_should_discourse'   # "we should take into account"
        if tok.i == tok.sent.start: return 'rule_should_conditional'               # "Should the copper be incorporated …"(가정 도치)
        if head.lemma_.lower() in DEONTIC_VERBS: return 'rule_should_deontic'      # 0.4.4: "CO gas … should be avoided"
        if re.match(r'For (an? |the )?(efficient|effective|successful|high|good|better|optimal)\b', tok.sent.text): return 'rule_should_deontic'   # 0.4.4: "For an efficient injection, … should be transferred"(요건)
    if lem in ('appear', 'seem') and any(c.dep_ == 'prep' and c.lower_ in LOCATION_PREPS for c in tok.children) \
            and not any(c.dep_ == 'xcomp' for c in tok.children) and not any(c.dep_ == 'ccomp' and any(g.lower_ == 'that' for g in c.children) for c in tok.children):
        return 'rule_appear_literal'                # 0.4.4: "The first one appears in the UV region"(위치)
    if lem in ('suggest', 'propose', 'claim', 'argue') and any(c.dep_ == 'nsubjpass' and c.lower_ == 'it' for c in tok.children) \
            and any(c.dep_ in ('aux', 'auxpass') and c.lower_ in ('has', 'have', 'had', 'was', 'were') for c in tok.children):
        return 'rule_reporting'                     # 0.4.4: "It has been suggested that …"(선행연구를 전함). 현재형 "It is suggested that"은 남긴다
    if lem == 'obviously' and tok.i > head.i and head.pos_ == 'VERB':
        return 'rule_booster_literal'               # 0.4.4: "k decreases obviously"(뚜렷하게, 정도)
    if lem == 'prove' and any(c.dep_ in ('xcomp', 'acomp', 'oprd') for c in tok.children):
        return 'rule_booster_literal'               # "proved to be unsuccessful", "has proven rather difficult"
    if lem in LITERAL_OBJ:
        if lem == 'establish' and tok.dep_ in ('amod', 'compound'): return 'rule_booster_literal'   # "well-established protocols"
        if any(c.dep_ in ('dobj', 'nsubjpass') and c.lemma_.lower() in LITERAL_OBJ[lem] for c in tok.children): return 'rule_booster_literal'
        if lem == 'demonstrate' and any(c.dep_ == 'prep' and any(g.lemma_.lower() in ('artwork', 'figure', 'scheme', 'table', 'abstract') for g in c.children) for c in tok.children):
            return 'rule_booster_literal'           # "demonstrated in the abstract and table of contents artwork"(보여 줌)
    if lem in ('clear', 'obvious', 'evident', 'definite'):
        if tok.dep_ == 'amod' and head.lemma_.lower() not in EVIDENCE_NOUNS: return 'rule_adj_attributive'   # "a clear shell", "no obvious diffraction feature"
        subj = [c for c in head.children if c.dep_ in ('nsubj', 'nsubjpass')] if tok.dep_ == 'acomp' else []
        if any(d.lower_ == 'no' for s in subj for d in s.children if d.dep_ == 'det'): return 'rule_adj_negated'   # "no aggregation was evident"
    # 부정·정도 수식(0.4.3): "is less clear", "It is not clear whether", "not clearly shown"은 확신이 아니다.
    # less·hardly는 낱말에 직접(advmod), not은 술어(is, shown)에 붙는다(neg)
    if lem in BOOSTER['adjective'][0] | BOOSTER['adverb'][0]:
        if any(c.dep_ in ('advmod', 'neg') and c.lemma_.lower() in WEAKENERS for c in tok.children): return 'rule_booster_negated'
        if tok.dep_ in ('acomp', 'advmod') and any(c.dep_ == 'neg' for c in head.children): return 'rule_booster_negated'
    if lem == 'possible':
        if tok.dep_ == 'acomp' and any(c.dep_ == 'xcomp' for c in head.children): return 'rule_possible_ability'   # "it was not possible to isolate"
        if tok.dep_ == 'amod' and head.lemma_.lower() in LITERAL_ADJ_HEAD['possible']: return 'rule_possible_literal'   # "possible alternative methods"
    return None

def classify(tok):
    lem, tag, pos = tok.lemma_.lower(), tok.tag_, tok.pos_
    for name, table in (('hedge', HEDGE), ('booster', BOOSTER), ('review', REVIEW_ONLY)):
        for cat, (lems, poss) in table.items():
            if lem in lems and (tag in poss or pos in poss):
                if cat == 'rounder':   # 'about'은 숫자 앞일 때만
                    nxt = tok.nbor(1) if tok.i + 1 < len(tok.doc) else None
                    if nxt is None or not (nxt.like_num or nxt.text[:1].isdigit()): continue
                if name in ('hedge', 'booster') and cat in ('verb', 'adjective') and not structural_ok(tok, lem): continue
                if name in ('hedge', 'booster'):
                    why = literal_reason(tok, lem)
                    if why: return 'review', why
                return name, cat
    return None, None

def main():
    ap = argparse.ArgumentParser(); ap.add_argument('ex_dir'); ap.add_argument('out_dir')
    ap.add_argument('--include-abstract', action='store_true'); ap.add_argument('--model', default='en_core_web_sm')
    ap.add_argument('--max-papers', type=int, default=10, help='Explicit corpus size override; counting and aggregation rules stay unchanged')
    a = ap.parse_args(); os.makedirs(a.out_dir, exist_ok=True)
    nlp = L.nlp(a.model)
    docs = load(a.ex_dir)
    checks = dict(version=VERSION, papers=len(docs), items=[])
    def chk(name, ok, detail=''): checks['items'].append(dict(check=name, result='Pass' if ok else 'Fail', detail=detail))
    chk(f'논문 수 2~{a.max_papers}편', 2 <= len(docs) <= a.max_papers, f'{len(docs)}편')
    per, evidence = [], []
    verbs = defaultdict(lambda: defaultdict(Counter))      # sec -> doc -> lemma counts
    words = defaultdict(Counter)                              # doc -> sec -> words
    for D, prose in docs:
        secs = Counter(s.section_type for s in D.sentences)
        chk(f'{D.document_id}: 서론과 결과·논의 절 있음', 'INT' in secs and ({'RD', 'RES', 'DIS'} & set(secs)), dict(secs))
        # DISCUSSION 절이 따로 없으면 RESULTS 절에서 해석도 함께 하므로 결과·논의(RD)로 묶는다
        res_as_rd = 'RES' in secs and not ({'DIS', 'RD'} & set(secs))
        if res_as_rd: chk(f'{D.document_id}: RESULTS 절만 있어 결과·논의로 묶음', True, f"RES {secs['RES']}문장")
        cnt = defaultdict(Counter)
        for s in D.sentences:
            if not prose.get(s.id, True): continue
            if s.section_type == 'ABS' and not a.include_abstract: continue
            sec = 'RD' if res_as_rd and s.section_type == 'RES' else s.section_type
            doc = nlp(s.text)
            nw = sum(1 for t in doc if t.is_alpha)
            words[D.document_id][sec] += nw
            _, hits, _ = L.analyze_sentence(D.document_id, s, a.model)
            prior_spans = [(h['start'], h['end']) for h in hits if h['role'] == 'prior']
            for t in doc:
                if t.pos_ == 'VERB': verbs[sec][D.document_id][t.lemma_.lower()] += 1
                name, cat = classify(t)
                if name and any(b <= t.idx < e for b, e in prior_spans): name = None   # 선행연구 보고로 이미 셈
                if name and (name == 'review' or sec in HEDGE_SECTIONS):
                    cnt[sec][f'{name}:{cat}'] += 1
                    evidence.append(dict(document_id=D.document_id, sentence_id=s.id, section=sec, category=f'{name}:{cat}', token=t.text, lemma=t.lemma_.lower(), sentence=s.text[:300]))
            # 여러 낱말 표현(Hyland 부록)
            if sec in HEDGE_SECTIONS:
                low = s.text.lower()
                for name, phrases in (('hedge', HEDGE_PHRASES), ('booster', BOOSTER_PHRASES)):
                    for ph in phrases:
                        for m in re.finditer(r'\b' + re.escape(ph) + r'\b', low):
                            cnt[sec][f'{name}:phrase'] += 1
                            evidence.append(dict(document_id=D.document_id, sentence_id=s.id, section=sec, category=f'{name}:phrase', token=s.text[m.start():m.end()], lemma=ph, sentence=s.text[:300]))
            # 보고동사(선행연구 보고): 같은 분석 엔진(engine_local) 기준
            for h in hits:
                if h['role'] == 'prior':
                    cnt[sec]['reporting:prior'] += 1
                    evidence.append(dict(document_id=D.document_id, sentence_id=s.id, section=sec, category='reporting:prior', token=h['text'], lemma=h.get('lemma', ''), sentence=s.text[:300]))
        for sec in words[D.document_id]:
            w = words[D.document_id][sec]
            c = cnt[sec]
            row = dict(document_id=D.document_id, section=sec, words=w,
                       hedge=sum(v for k, v in c.items() if k.startswith('hedge:')),
                       booster=sum(v for k, v in c.items() if k.startswith('booster:')),
                       reporting=c['reporting:prior'], verbs=sum(verbs[sec][D.document_id].values()))
            for k in REVIEW_ONLY: row[f'{k}_review'] = c[f'review:{k}']
            row['rule_excluded'] = sum(v for k, v in c.items() if k.startswith('review:rule_'))   # 0.4.2 오판 규칙으로 뺀 개수
            for k in ('hedge:modal', 'hedge:verb', 'hedge:adverb', 'hedge:adjective', 'hedge:phrase', 'booster:verb', 'booster:adverb', 'booster:adjective', 'booster:phrase'): row[k] = c[k]
            for k in ('hedge', 'booster', 'reporting', 'verbs'):
                row[f'{k}_per1000'] = round(row[k] / w * 1000, 2) if w else None
            if sec not in HEDGE_SECTIONS: row['hedge_per1000'] = row['booster_per1000'] = None   # 실험 절은 헷지 분모에서 제외
            per.append(row)
        chk(f'{D.document_id}: 분석 단어 수 1,000 이상', sum(words[D.document_id].values()) >= 1000, sum(words[D.document_id].values()))
    # 기준선: 절 × 지표의 중간값·범위
    base = []
    for sec in SECTIONS:
        rows = [r for r in per if r['section'] == sec]
        for m in ('hedge_per1000', 'booster_per1000', 'reporting_per1000', 'verbs_per1000', 'words'):
            vals = [r[m] for r in rows if r[m] is not None]
            if not vals: continue
            base.append(dict(section=sec, metric=m, n_papers=len(vals), median=round(statistics.median(vals), 2), min=min(vals), max=max(vals),
                             values=' '.join(f"{r['document_id']}={r[m]}" for r in rows if r[m] is not None)))
    # 공통 동사: 절반 이상 논문에서 나온 동사, 1,000단어당 중간값 순
    common = []
    for sec in SECTIONS:
        ds = [d for d in verbs[sec] if words[d][sec]]
        if not ds: continue
        need = math.ceil(len(ds) / 2)
        lem_docs = Counter(l for d in ds for l in verbs[sec][d])
        for lem, nd in lem_docs.items():
            if nd < need: continue
            rates = [verbs[sec][d][lem] / words[d][sec] * 1000 for d in ds]
            common.append(dict(section=sec, lemma=lem, papers_with=nd, papers_in_section=len(ds), median_per1000=round(statistics.median(rates), 2),
                               total=sum(verbs[sec][d][lem] for d in ds)))
    common.sort(key=lambda r: (SECTIONS.index(r['section']), -r['median_per1000']))
    def wcsv(name, rows):
        if not rows: return
        with open(os.path.join(a.out_dir, name), 'w', encoding='utf-8-sig', newline='') as f:
            w = csv.DictWriter(f, fieldnames=list(rows[0].keys())); w.writeheader(); w.writerows(rows)
    wcsv('per_paper.csv', per); wcsv('baseline.csv', base); wcsv('common_verbs.csv', common); wcsv('evidence.csv', evidence)
    checks['model'] = a.model; checks['include_abstract'] = a.include_abstract
    json.dump(checks, open(os.path.join(a.out_dir, 'checks.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    lab = {'ABS': '초록', 'INT': '서론', 'MET': '실험·방법', 'RES': '결과', 'DIS': '논의', 'RD': '결과·논의', 'CON': '결론'}
    mlab = {'hedge_per1000': '헷지/1,000단어', 'booster_per1000': '비헷지(강조)/1,000단어', 'reporting_per1000': '보고동사(선행연구)/1,000단어', 'verbs_per1000': '동사 전체/1,000단어', 'words': '분석 단어 수'}
    md = [f'# 섹션별 동사·헷지 기준선 (Stage 1, {VERSION})', '', f'- 논문 {len(docs)}편: ' + ', '.join(D.document_id for D, _ in docs),
          '- 값은 중간값(최솟값~최댓값). 편수가 적으므로 경향을 단정하지 않는다. 모든 개수의 근거 문장은 evidence.csv에 있다.',
          '- 헷지·비헷지 목록은 Hyland (2005) Metadiscourse 부록(pp. 218-223)을 따른다. 실험·방법 절은 분모에서 뺐다.',
          '- Hyland 목록 가운데 can, 어림말(about 등), 정도·빈도 부사(relatively, often 등), must, show·find·estimate, apparent·typical은 화학에서 문자 그대로 쓰이는 경우가 많아 합계에 넣지 않고 확인 후보로만 셌다. Hyland 부록에 없는 팀 추가 낱말(confirm, propose 등)도 확인 후보로 돌렸다.', '',
          '| 절 | 지표 | 편수 | 중간값 | 범위 |', '|---|---|---|---|---|']
    for b in base:
        md.append(f"| {lab.get(b['section'], b['section'])} | {mlab[b['metric']]} | {b['n_papers']} | {b['median']} | {b['min']}~{b['max']} |")
    md += ['', '## 절별 공통 동사(절반 이상 논문에 나온 동사, 상위 10)', '']
    for sec in SECTIONS:
        cs_ = [c for c in common if c['section'] == sec][:10]
        if cs_: md.append(f"- {lab.get(sec, sec)}: " + ', '.join(f"{c['lemma']} {c['median_per1000']} ({c['papers_with']}/{c['papers_in_section']}편)" for c in cs_))
    md += ['', '## 처리 검사', ''] + [f"- {c['result']}: {c['check']} ({c['detail']})" for c in checks['items']]
    open(os.path.join(a.out_dir, 'baseline_report.md'), 'w', encoding='utf-8').write('\n'.join(md) + '\n')
    print(json.dumps({'papers': len(docs), 'checks_failed': [c for c in checks['items'] if c['result'] == 'Fail'], 'baseline_rows': len(base)}, ensure_ascii=False))

if __name__ == '__main__':
    main()
