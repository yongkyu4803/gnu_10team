"""
engine_local — 외부 AI API를 호출하지 않는 분석 엔진(spaCy 구문분석 + 규칙)

- 기본은 '독립 분석' 모드: 초안 주석 CSV를 전혀 쓰지 않는다.
- use_annotations=True는 별도 모드: CSV의 선행연구 보고 표현을 그대로 가져와 표시한다(source=annotation_reuse).
  이 모드의 결과를 그 CSV와 비교해 일치도를 내면 안 된다(같은 자료를 되비추는 것이므로).
- 결과는 후보이며 판정 완료가 아니다. role은 도구의 역할 분류이지 Hyland(2001)의 분류 자체가 아니다.
규칙 판본: whole-paper-0.4.1 (0.3.3을 바탕으로 독립 모드의 선행연구 판정·core 층 출력을 추가.
0.4.1: "found in Table 3"을 그림·표 지시로, "Smith et al. [5]"처럼 분석기가 잘못 끊은 인용 주어를 선행연구로 판정.
0.4.2: "Chen et al.[32] reported"처럼 분석기가 주어를 찾지 못해도, 동사 바로 앞이 "저자명 + 인용 번호"이면 주어를 선행연구로 판정)
"""
import re
import rvtool as rv

RULE_VERSION = "whole-paper-0.4.2"
METHOD = set("""use utilize utilise perform prepare measure determine analyze analyse extract evaluate compare conduct
investigate examine calculate quantify dilute mix combine heat stir filter centrifuge dry store weigh inject record
acquire apply adapt test assess characterize characterise select add repeat set cool dissolve separate collect purchase
calibrate carry optimize optimise treat wash grind sieve incubate homogenize homogenise decant agitate employ run
adjust follow estimate compute fit model simulate study develop recover reuse""".split())
RESULT = set("show find observe demonstrate reveal exhibit confirm display detect verify".split())
INTERP = set("""suggest indicate imply explain attribute ascribe conclude propose argue believe assume expect appear seem
consider hypothesize hypothesise speculate infer interpret support stipulate""".split())
REPORT = set("report describe state claim highlight note mention point emphasize emphasise document cite".split())
REF_LEMMAS = {"find","show","present","illustrate","depict","summarize","summarise","display","list","give","provide","compare","plot","see","mention","describe","discuss","note","report","detail"}
INTERNAL = {"above","below","earlier","later"}
FIG = re.compile(r"^(figure|figures|fig|figs|table|tables|scheme|schemes|supplementary|eq|equation|section)$", re.I)
WE = re.compile(r"\b(we|our|us)\b|^(this|the present) (study|work|paper)", re.I)
PRIORW = re.compile(r"(et al|studies|literature|researchers|authors|reference|references|\bref\b|refs|research|previous|prior|other works|coworkers)", re.I)
DATAW = re.compile(r"(data|result|measurement|analys|spectr|value|sample|extract|yield|content|test|experiment|curve|signal|peak|composition|observation|characteri|rheolog|viscosit|concentration|profile|chromatogram)", re.I)
MATW = re.compile(r"(\bdes\b|nades|solvent|bsg|\bmd\b|biomass|compound|acid|chcl|mixture|grain|dust|lignin|cellulose|phenol|water|ethanol|acetone|\bpc\b|\bma\b|\bgly\b)", re.I)
CITE = re.compile(r"\[\d[\d,\s–−-]*\]")
NAMED = re.compile(r"(?:\bet al\.|\band coworkers|\b[A-Z][a-zà-ÿ'’\-]+ and [A-Z][a-zà-ÿ'’\-]+|\b(?:by|of|from)\s+(?:van |de |von |der )?[A-Za-z][a-zà-ÿ'’\-]+(?: and [A-Z][a-zà-ÿ\-]+)?)\s*(?=\[\d)")

_NLP = {}
def nlp(model="en_core_web_sm"):
    if model not in _NLP:
        import spacy
        _NLP[model] = spacy.load(model)
    return _NLP[model]

def lemma_of(tok):
    l = tok.lemma_.lower()
    if l in ("carry", "point") and any(c.dep_ == "prt" and c.lower_ == "out" for c in tok.children): return l + " out"
    if l == "rely": return "rely on"
    return l

def classify_agent(t):
    t = t.strip()
    if not t: return None
    if WE.search(t): return "필자"
    first = t.split()[0]
    if FIG.match(first.strip("(")): return "그림·표"
    if CITE.search(t) or PRIORW.search(t): return "선행연구"
    if DATAW.search(t): return "자료·측정"
    if MATW.search(t): return "연구 대상(물질·시료)"
    if re.match(r"^(this|these|it|which|that)\b", t, re.I): return "앞 내용 지시"
    return None

AUTHOR_CITE_BEFORE = re.compile(
    r"((?:[A-Z][A-Za-zà-ÿ'’\-]+(?:\s+(?:and|&)\s+[A-Z][A-Za-zà-ÿ'’\-]+)?\s+et\s+al\.?"
    r"|[A-Z][A-Za-zà-ÿ'’\-]+\s+and\s+(?:coworkers|colleagues|co-workers|[A-Z][A-Za-zà-ÿ'’\-]+))"
    r"\s*\[\d[\d,\s–−-]*\](?:\s*[−–,-]\s*\[\d[\d,\s–−-]*\])*)"
    r"\s*(?:(?:have|has|had|also|previously|recently|further|then|first)\s+)*$")

def author_before(tok):
    """동사(조동사 포함) 바로 앞이 '저자명 + 인용 번호'인지 원문 문자열로 확인한다(구문분석이 주어를 놓쳤을 때)."""
    start = min([c.idx for c in tok.children if c.dep_ in ("aux", "auxpass", "neg") and c.i < tok.i] + [tok.idx])
    m = AUTHOR_CITE_BEFORE.search(tok.doc.text[:start])
    return m.group(1).strip() if m else None

def agent_of(tok):
    sub = lambda w: "".join(x.text_with_ws for x in w.subtree).strip()
    agt = [c for c in tok.children if c.dep_ == "agent"]
    subj = [c for c in tok.children if c.dep_ in ("nsubj","nsubjpass","csubj","csubjpass")]
    if not subj and tok.dep_ in ("acl","relcl"): subj = [tok.head]
    if not subj and tok.dep_ in ("conj","xcomp","advcl") and tok.head.pos_ in ("VERB","AUX"):
        subj = [c for c in tok.head.children if c.dep_ in ("nsubj","nsubjpass")]
    for a in agt:
        k = classify_agent(re.sub(r"^by\s+", "", sub(a)))
        if k: return k, sub(a)
    # 구문분석이 주어를 찾지 못했거나 범주를 정하지 못한 경우에만 원문 문자열로 보완한다
    if all(classify_agent(sub(x)) is None for x in subj):
        ab = author_before(tok)
        if ab: return "선행연구", ab
    for s in subj:
        txt = s.text if tok.dep_ in ("acl","relcl") else sub(s)
        k = classify_agent(txt)
        # 'Smith et al. [5] showed'에서 spaCy 기본 모델이 'et al.' 뒤를 끊어 주어가 '5]'만 남는 경우: 인용 번호가 주어 → 선행연구
        if k is None and re.fullmatch(r"[\[\]\d,\s–−-]+", txt.strip()): k = "선행연구"
        return (k or "기타"), txt
    passive = any(c.dep_ == "auxpass" for c in tok.children) or tok.tag_ == "VBN"
    return ("수동(행위자 생략)" if passive else "불명"), ""

def is_ref_pointer(tok):
    if any(c.dep_ == "advmod" and c.lower_ in INTERNAL for c in tok.children) and not CITE.search(tok.sent.text): return True
    for c in tok.children:
        if c.dep_ in ("nsubj","nsubjpass") and any(FIG.match(w.text) for w in c.subtree): return True
        if c.dep_ == "prep" and any(FIG.match(g.text) for g in c.subtree): return True
    return False

def span_of(tok):
    doc = tok.doc
    left = [c for c in tok.children if c.dep_ in ("aux","auxpass","neg") and c.i < tok.i]
    start = min([c.i for c in left], default=tok.i)
    if doc[start].dep_ not in ("aux","auxpass","neg"): start = tok.i
    end = tok.i
    lem = lemma_of(tok)
    if lem in ("carry out","point out"): end = max([c.i for c in tok.children if c.dep_ == "prt"], default=end)
    if lem == "rely on": end = max([c.i for c in tok.children if c.dep_ == "prep" and c.lower_ == "on"], default=end)
    return doc[start].idx, doc[end].idx + len(doc[end].text)

def citation_form(text):
    """코드 규칙: 이름(et al., X and Y, by/of X)이 바로 앞에 붙은 인용은 통합, 번호만 있으면 비통합, 둘 다 있으면 혼합(빈 값)."""
    brackets = list(CITE.finditer(text))
    if not brackets: return "", ""
    named_pos = {m.end() for m in NAMED.finditer(text)}
    named = [b for b in brackets if any(abs(b.start() - p) <= 1 for p in named_pos)]
    if named and len(named) < len(brackets): return "", "혼합 인용 후보: 이름이 붙은 인용과 번호만 있는 인용이 함께 있음(보류)"
    return ("integral" if named else "non_integral"), ""

def analyze_sentence(doc_id, s, model, use_annotations=False, ann=None):
    d = nlp(model)(s.text)
    has_cite = bool(rv.citation_numbers(s.text))
    hits, taken, excluded = [], [], []
    def drop(tok, why): excluded.append(dict(document_id=doc_id, sentence_id=s.id, text=tok.text, start=tok.idx, end=tok.idx+len(tok.text), lemma=lemma_of(tok), reason=why))
    if use_annotations and ann:
        pos = 0
        for v in [x for x in ann.get("reporting_verb", "").split(", ") if x]:
            i = s.text.find(v, pos)
            if i < 0: excluded.append(dict(document_id=doc_id, sentence_id=s.id, text=v, start=0, end=0, lemma="", reason="주석 재사용: 원문에서 표현을 찾지 못함")); continue
            hits.append(dict(document_id=doc_id, sentence_id=s.id, text=v, start=i, end=i+len(v), role="prior", attr="선행연구",
                             source="annotation_reuse", agent="선행연구", lemma=v.split()[-1].lower(), note="초안 주석 CSV에서 가져옴(독립 탐지 아님)"))
            taken.append((i, i+len(v))); pos = i+len(v)
    for tok in d:
        if tok.pos_ != "VERB": continue
        lem = lemma_of(tok); base = lem.split()[0]
        cls = ("method" if base in METHOD else "result" if base in RESULT else "interpret" if base in INTERP
               else "report" if base in REPORT else None)
        if not cls: continue
        has_aux = any(c.dep_ in ("aux","auxpass") for c in tok.children)
        if tok.dep_ == "amod": drop(tok, "형용사적 분사(amod)"); continue
        if tok.tag_ == "VB" and any(c.dep_ == "aux" and c.lower_ == "to" for c in tok.children): drop(tok, "to부정사"); continue
        b, e = span_of(tok)
        if any(b < te and e > tb for tb, te in taken): continue
        agent, agent_txt = agent_of(tok)
        sub_cite = bool(CITE.search("".join(w.text_with_ws for w in tok.subtree)))
        prior_link = agent == "선행연구" or sub_cite
        if base in REF_LEMMAS and is_ref_pointer(tok): role, attr = "ref", "현재 연구(본문 지시)"
        elif has_cite and prior_link: role, attr = "prior", "선행연구"
        elif cls == "method":
            if tok.tag_ == "VBG" and not has_aux: drop(tok, "조동사 없는 동명사(방법 동사)"); continue
            if tok.dep_ in ("prep","acl") and not has_aux: drop(tok, "전치사적 용법 또는 명사 수식 분사(방법 동사)"); continue
            role, attr = "method", ("현재 연구" if not has_cite or agent == "필자" else "불명")
        elif has_cite: role, attr = ("result" if cls != "interpret" else "interpret", "현재 연구") if agent in ("필자","자료·측정","그림·표") else ("uncertain", "불명")
        elif cls == "report": role, attr = ("result", "현재 연구") if agent == "필자" else ("uncertain", "불명")
        else: role, attr = cls, "현재 연구"
        note = ""
        if role == "uncertain": note = "인용 문장 안의 후보: 선행연구 보고인지 자기 연구 서술인지 검토 필요" if has_cite else "보고 대상의 귀속 검토 필요"
        h = dict(document_id=doc_id, sentence_id=s.id, text=s.text[b:e], start=b, end=e, role=role, attr=attr, source="local_rules",
                 agent=agent, lemma=lem)
        if agent_txt: h["agent_text"] = agent_txt[:80]
        if note: h["note"] = note
        hits.append(h); taken.append((b, e))
    hits.sort(key=lambda h: h["start"])
    # core(v1.3) 층
    nums = rv.citation_numbers(s.text)
    if has_cite:
        form, fnote = citation_form(s.text)
        prior = [h["text"] for h in hits if h["role"] == "prior"]
        notes = [x for x in [fnote, ("주석 재사용 모드" if use_annotations else "로컬 규칙 결과(판정 완료 아님)")] if x]
        core = dict(document_id=doc_id, sentence_id=s.id, has_citation=True, citation_numbers=nums,
                    reporting_verb=", ".join(prior), citation_form=form, note="; ".join(notes))
    else:
        core = dict(document_id=doc_id, sentence_id=s.id, has_citation=False, citation_numbers=[], reporting_verb="", citation_form="", note="")
    return core, hits, excluded

def analyze(doc, sentence_ids=None, model="en_core_web_sm", use_annotations=False):
    """문서 전체(또는 지정 문장)를 분석해 (core, whole, excluded, record_fields)를 돌려준다."""
    import spacy
    m = doc.by_id(); ids = sentence_ids or [s.id for s in doc.sentences]
    unknown = [i for i in ids if i not in m]
    if unknown: raise rv.InputError(f"입력에 없는 문장 ID: {unknown}")
    core, whole, excl = [], [], []
    for i in ids:
        c, h, e = analyze_sentence(doc.document_id, m[i], model, use_annotations, doc.annotations.get(i))
        core.append(c); whole += h; excl += e
    n = nlp(model)
    fields = dict(model=model, model_version=n.meta.get("version"), spacy=spacy.__version__, rule_version=RULE_VERSION,
                  use_annotations=use_annotations, api_called=False,
                  processing=dict(requested=len(ids), requested_ids=list(ids), succeeded=len(ids), failed=0, failed_ids=[]),
                  excluded=len(excl))
    return core, whole, excl, fields
