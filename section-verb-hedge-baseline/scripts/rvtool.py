"""
rvtool — 보고동사로 다시 읽기: 두 코랩 노트북이 함께 쓰는 공통 모듈

담당: 입력 검사, 인용 번호 정규화, 저장(덮어쓰기 금지), 다시 읽기, 결과 검증,
      초안 주석과의 일치도(정확도 아님), 화면(HTML) 연결.
분석 엔진은 engine_local.py(외부 API 없음)와 engine_api.py(실제 API)에 따로 있다.

두 층의 출력
- core  : 입력데이터 명세서 v1.3의 문장별 결과(분석출력 JSON Schema v1.3, 수정 없이 사용)
- whole : 논문 전체 표현별 hits(별도 확장 스키마 whole_paper_hits v0.1)
위치(start,end)는 원문 문자열의 Python 유니코드 코드포인트 기준 [start,end)이다.
화면용으로만 JavaScript UTF-16 위치로 바꾼다.
"""
from __future__ import annotations
import csv, hashlib, json, os, re, datetime, uuid, html as _html
from dataclasses import dataclass, field

TOOL_VERSION = "rvtool-1.3.0"
CORE_SCHEMA_VERSION = "1.3"
WHOLE_SCHEMA_VERSION = "whole_paper_hits-0.1"
HERE = os.path.dirname(os.path.abspath(__file__))
ID_RE = re.compile(r"^\d+(?:\.\d+)*-\d{3,}$")
CITE_RE = re.compile(r"\[([1-9][\d,\s–−-]*)\](?:\s*[−–-]\s*\[(\d+)\])?")   # 0으로 시작하는 [047−1748](ICDD 번호)은 인용이 아님
ROLES = ["prior", "result", "interpret", "method", "ref", "uncertain"]
ATTRS = ["선행연구", "현재 연구", "현재 연구(본문 지시)", "불명"]
SMOKE = [("paper_a", "3.2.3-007"), ("paper_a", "3.3.1-012")]

class InputError(ValueError):
    pass

class ValidationFailed(ValueError):
    """저장 전 검증에서 문제가 나와 저장하지 않았을 때."""

def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 16), b""): h.update(chunk)
    return h.hexdigest()

def now_iso():
    return datetime.datetime.now().astimezone().isoformat(timespec="seconds")

# ---------------------------------------------------------------- 입력
@dataclass
class Sentence:
    id: str; order: int; text: str; section_type: str; section_label: str
    section_title: str; paragraph_id: str; sentence_in_paragraph: int; word_count: int

@dataclass
class Document:
    document_id: str; document_version: str; meta: dict; sentences: list
    paths: dict; hashes: dict; annotations: dict = field(default_factory=dict)
    def by_id(self): return {s.id: s for s in self.sentences}

def read_txt(path):
    meta, rows, seen_body = {}, [], False
    with open(path, encoding="utf-8-sig") as f:
        for n, line in enumerate(f, 1):
            line = line.rstrip("\r\n")
            if not line.strip(): continue
            if line.startswith("#") and not seen_body:
                k, _, v = line[1:].partition(":"); meta[k.strip()] = v.strip(); continue
            seen_body = True
            sid, tab, text = line.partition("\t")
            if not tab: raise InputError(f"{path}:{n} 탭이 없는 행")
            if "\t" in text: raise InputError(f"{path}:{n} 문장 안에 탭이 있습니다(조용히 고치지 않음)")
            if not ID_RE.match(sid): raise InputError(f"{path}:{n} 문장 ID 형식 오류: {sid}")
            if not text.strip(): raise InputError(f"{path}:{n} 빈 문장: {sid}")
            rows.append((sid, text))
    ids = [r[0] for r in rows]
    dup = sorted({i for i in ids if ids.count(i) > 1})
    if dup: raise InputError(f"{path} 중복 문장 ID: {dup[:5]}")
    return meta, rows

def load_document(txt, tsv, document_id=None, annotations_csv=None, document_version=None):
    """TXT·구조 TSV(·선택: 초안 주석 CSV)를 읽고 모두 검사한다. 문장을 다시 나누거나 ID를 바꾸지 않는다."""
    meta, rows = read_txt(txt)
    did = document_id or meta.get("document_id")
    if not did: raise InputError("document_id가 없습니다(머리부나 인자로 주세요)")
    if meta.get("document_id") and meta["document_id"] != did: raise InputError("머리부 document_id와 인자가 다릅니다")
    trows = list(csv.DictReader(open(tsv, encoding="utf-8-sig"), delimiter="\t"))
    tids = [r["sentence_id"] for r in trows]
    if len(tids) != len(set(tids)): raise InputError("구조 TSV에 중복 문장 ID")
    if {r["document_id"] for r in trows} != {did}: raise InputError("구조 TSV의 document_id 불일치")
    if [r[0] for r in rows] != tids: raise InputError("TXT와 구조 TSV의 문장 ID 순서가 다릅니다")
    if [int(r["order"]) for r in trows] != list(range(1, len(trows) + 1)): raise InputError("구조 TSV의 order가 1부터 연속이 아닙니다")
    sents = [Sentence(r[0], int(t["order"]), r[1], t["section_type"], t["section_label"], t["section_title"],
                      t["paragraph_id"], int(t["sentence_in_paragraph"]), int(t["word_count"])) for r, t in zip(rows, trows)]
    paths = dict(txt=txt, tsv=tsv); hashes = dict(txt=sha256_file(txt), tsv=sha256_file(tsv))
    ann = {}
    if annotations_csv:
        krows = list(csv.DictReader(open(annotations_csv, encoding="utf-8-sig")))
        kids = [r["sentence_id"] for r in krows]
        if len(kids) != len(set(kids)): raise InputError("주석 CSV에 중복 문장 ID")
        textmap = dict(rows)
        for r in krows:
            if r.get("document_id") and r["document_id"] != did: raise InputError(f"주석 CSV document_id 불일치: {r['sentence_id']}")
            if r["sentence_id"] not in textmap: raise InputError(f"주석 CSV에만 있는 문장 ID: {r['sentence_id']}")
            if r.get("sentence") and r["sentence"] != textmap[r["sentence_id"]]: raise InputError(f"주석 CSV 문장이 TXT와 다름: {r['sentence_id']}")
            ann[r["sentence_id"]] = r
        paths["annotations"] = annotations_csv; hashes["annotations"] = sha256_file(annotations_csv)
    ver = document_version or meta.get("document_version") or "unversioned"
    return Document(did, ver, meta, sents, paths, hashes, ann)

def describe(doc):
    from collections import Counter
    c = Counter(s.section_type for s in doc.sentences)
    return dict(document_id=doc.document_id, document_version=doc.document_version, sentences=len(doc.sentences),
                paragraphs=len({s.paragraph_id for s in doc.sentences}), by_section=dict(c),
                citing_sentences=sum(1 for s in doc.sentences if citation_numbers(s.text)),
                annotations_loaded=bool(doc.annotations), hashes=doc.hashes)

def check_preprocessing_record(doc):
    """입력 TXT 머리부의 전처리 기록(총 문장 수·총 문단 수·인용 표지 문장 수)과 실제로 읽은 값을 비교한다.
    기록이 없는 항목은 '기록 없음'으로 두고 비교하지 않는다. 이 검사는 '전처리 출력이 온전히 전달되었는가'를 보며,
    원문 충실성(문장 경계가 원문과 맞는지)은 전처리 단계에서 따로 확인한다."""
    def num(key):
        v = doc.meta.get(key)
        m = re.match(r"\s*(\d+)", v) if v else None
        return int(m.group(1)) if m else None
    actual = {"총 문장 수": len(doc.sentences), "총 문단 수": len({s.paragraph_id for s in doc.sentences}),
              "인용 표지 문장 수": sum(1 for s in doc.sentences if citation_numbers(s.text))}
    rows = []
    for k, a in actual.items():
        r = num(k)
        rows.append(dict(item=k, record=r, actual=a, status=("기록 없음" if r is None else "일치" if r == a else "불일치")))
    return rows

# ---------------------------------------------------------------- 인용 번호(코드로 판정)
def citation_numbers(text):
    """[23–25]→23,24,25 / [23]−[25]→23,24,25 / 중복 제거·정렬. 원문은 바꾸지 않는다."""
    nums = []
    for m in CITE_RE.finditer(text):
        part_nums = []
        for part in m.group(1).split(","):
            part = part.strip()
            r = re.match(r"^(\d+)\s*[–−-]\s*(\d+)$", part)
            if r:
                a, b = int(r.group(1)), int(r.group(2))
                if b < a or b - a > 200: raise InputError(f"해석할 수 없는 인용 범위: [{part}]")
                part_nums += list(range(a, b + 1))
            elif part.isdigit(): part_nums.append(int(part))
        if m.group(2):
            end = int(m.group(2))
            if part_nums and end >= part_nums[-1]: part_nums += list(range(part_nums[-1] + 1, end + 1))
        nums += part_nums
    return sorted(set(n for n in nums if n >= 1))

# ---------------------------------------------------------------- 저장(덮어쓰기 금지)
def new_run_id(engine):
    return f"{datetime.datetime.now().strftime('%Y%m%d-%H%M%S')}-{engine}-{uuid.uuid4().hex[:6]}"

def run_dir(root, doc, run_id):
    return os.path.join(root, doc.document_id, run_id)

def write_json_once(path, obj):
    if os.path.exists(path): raise FileExistsError(f"이미 있는 파일은 덮어쓰지 않습니다: {path}")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "x", encoding="utf-8") as f: json.dump(obj, f, ensure_ascii=False, indent=1)
    return sha256_file(path)

def save_run(root, doc, run_id, record, core, whole, extra=None):
    """결과 한 벌을 새 폴더에 저장한다. 같은 run_id가 있으면 멈춘다."""
    d = run_dir(root, doc, run_id)
    if os.path.exists(os.path.join(d, "run.json")): raise FileExistsError(f"이미 저장된 실행입니다: {d}")
    out_hash = dict(core=write_json_once(os.path.join(d, "core.json"), core),
                    whole=write_json_once(os.path.join(d, "whole.json"), whole))
    for name, obj in (extra or {}).items(): out_hash[name] = write_json_once(os.path.join(d, f"{name}.json"), obj)
    record = dict(record, output_sha256=out_hash, saved_at=now_iso(), run_dir=d)
    write_json_once(os.path.join(d, "run.json"), record)
    return d

def save_validated_run(root, doc, run_id, record, core, whole, extra=None, expected_ids=None):
    """core·whole을 먼저 검증하고, 문제가 없을 때만 저장한다. 문제가 있으면 아무것도 저장하지 않고 ValidationFailed."""
    problems = dict(core=validate_core(core, doc, expected_ids), whole=validate_whole(whole, doc))
    if problems["core"] or problems["whole"]:
        raise ValidationFailed(f"검증 실패로 저장하지 않았습니다(core {len(problems['core'])}건, whole {len(problems['whole'])}건): "
                               f"{(problems['core'] + problems['whole'])[:3]}")
    record = dict(record, validation=dict(core="통과", whole="통과", checked_at=now_iso()))
    return save_run(root, doc, run_id, record, core, whole, extra)

def list_runs(root, document_id=None):
    out = []
    if not os.path.isdir(root): return out
    for did in sorted(os.listdir(root)):
        if document_id and did != document_id: continue
        for rid in sorted(os.listdir(os.path.join(root, did))):
            p = os.path.join(root, did, rid, "run.json")
            if os.path.exists(p):
                r = json.load(open(p, encoding="utf-8")); out.append(dict(document_id=did, run_id=rid, engine=r.get("engine"),
                    scope=r.get("analysis_scope"), run_kind=r.get("run_kind", "full"), saved_at=r.get("saved_at"),
                    status={k: v for k, v in r.get("processing", {}).items() if k != "requested_ids"}))
    return out

def load_run(root, document_id, run_id, verify_hash=True):
    d = os.path.join(root, document_id, run_id)
    rec = json.load(open(os.path.join(d, "run.json"), encoding="utf-8"))
    if verify_hash:
        for name, h in rec["output_sha256"].items():
            if sha256_file(os.path.join(d, f"{name}.json")) != h: raise ValueError(f"저장 후 바뀐 파일: {name}.json")
    load = lambda n: json.load(open(os.path.join(d, f"{n}.json"), encoding="utf-8"))
    return dict(record=rec, core=load("core"), whole=load("whole"))

def base_record(doc, engine, run_id, scope, **kw):
    return dict(run_id=run_id, tool_version=TOOL_VERSION, engine=engine, analysis_scope=scope,
                document_id=doc.document_id, document_version=doc.document_version, input_sha256=doc.hashes,
                core_schema=CORE_SCHEMA_VERSION, whole_schema=WHOLE_SCHEMA_VERSION, started_at=now_iso(), **kw)

# ---------------------------------------------------------------- 검증
def _schema(name):
    return json.load(open(os.path.join(HERE, "schemas", name), encoding="utf-8"))

def validate_core(core, doc, expected_ids=None):
    """스키마(v1.3, 수정 없음) + ID 대응(누락·중복·미등록) 검사. 문제 목록을 돌려준다(빈 목록이면 통과)."""
    import jsonschema
    problems = []
    v = jsonschema.Draft202012Validator(_schema("core_v1.3.json"))
    for e in v.iter_errors(core): problems.append(f"스키마: {list(e.path)} {e.message[:160]}")
    ids = [r.get("sentence_id") for r in core]
    exp = list(expected_ids) if expected_ids is not None else [s.id for s in doc.sentences]
    known = {s.id for s in doc.sentences}
    dup = sorted({i for i in ids if ids.count(i) > 1})
    if dup: problems.append(f"중복 결과 ID: {dup[:5]}")
    unknown = sorted(set(ids) - known)
    if unknown: problems.append(f"입력에 없는 ID: {unknown[:5]}")
    missing = [i for i in exp if i not in set(ids)]
    if missing: problems.append(f"누락 ID {len(missing)}개: {missing[:5]}")
    if any(r.get("document_id") != doc.document_id for r in core): problems.append("document_id 불일치 결과가 있습니다")
    return problems

def validate_whole(hits, doc):
    import jsonschema
    problems = []
    v = jsonschema.Draft202012Validator(_schema("whole_paper_hits_v0.1.json"))
    for e in v.iter_errors(hits): problems.append(f"스키마: {list(e.path)} {e.message[:160]}")
    m = doc.by_id()
    for h in hits:
        s = m.get(h.get("sentence_id"))
        if s is None: problems.append(f"입력에 없는 ID: {h.get('sentence_id')}"); continue
        if s.text[h["start"]:h["end"]] != h["text"]: problems.append(f"위치 불일치: {h['sentence_id']} [{h['start']},{h['end']}) '{h['text']}'")
    return problems

# ---------------------------------------------------------------- 초안 주석과의 일치도(정확도 아님)
def agreement_with_annotations(core, doc, mode_note=""):
    """Claude 판정 초안(사람 미확인)과의 일치도와 불일치 후보. '정확도'라고 부르지 않는다."""
    if not doc.annotations: return None
    rows, n = [], dict(sentences=0, citation_numbers_same=0, has_verb_same=0, verb_text_same=0, form_same=0, pending_in_draft=0)
    for r in core:
        a = doc.annotations.get(r["sentence_id"]);
        if a is None: continue
        if a.get("has_citation") != "TRUE": continue
        n["sentences"] += 1
        a_nums = [int(x) for x in a["citation_numbers"].split(";") if x]
        a_verb = a.get("reporting_verb", ""); a_form = a.get("citation_form", "")
        if (a.get("note", "").startswith("경계") or (not a_verb and not a_form)): n["pending_in_draft"] += 1
        same_n = a_nums == r["citation_numbers"]; same_has = bool(a_verb) == bool(r["reporting_verb"])
        same_v = a_verb == r["reporting_verb"]; same_f = a_form == r["citation_form"]
        n["citation_numbers_same"] += same_n; n["has_verb_same"] += same_has; n["verb_text_same"] += same_v; n["form_same"] += same_f
        diffs = [k for k, ok in (("인용 번호", same_n), ("보고동사 유무", same_has), ("보고동사 문자열", same_v), ("인용 방식", same_f)) if not ok]
        if diffs:
            rows.append(dict(sentence_id=r["sentence_id"], differences=diffs, draft_verb=a_verb, result_verb=r["reporting_verb"],
                             draft_form=a_form, result_form=r["citation_form"], draft_numbers=a_nums, result_numbers=r["citation_numbers"]))
    return dict(label="Claude 판정 초안과의 일치도(사람이 확인한 정답이 아니므로 정확도가 아님)", note=mode_note, counts=n, disagreement_candidates=rows)

# ---------------------------------------------------------------- 집계
def aggregate(doc, hits, exclude_abstract=True, failed_ids=()):
    from collections import defaultdict
    words, cnt = defaultdict(int), defaultdict(lambda: defaultdict(int))
    for s in doc.sentences:
        if exclude_abstract and s.section_type == "ABS": continue
        words[s.section_type] += s.word_count
    m = doc.by_id()
    for h in hits:
        s = m[h["sentence_id"]]
        if exclude_abstract and s.section_type == "ABS": continue
        cnt[s.section_type][h["role"]] += 1
    rows = []
    for t in ["ABS", "INT", "MET", "RD", "CON"]:
        if t not in words: continue
        for r in ROLES:
            c = cnt[t][r]; rows.append(dict(section_type=t, role=r, count=c, words=words[t], per_1000_words=round(c / words[t] * 1000, 2) if words[t] else None))
    return dict(unit="표현(hit)", denominator="절별 단어 수", exclude_abstract=exclude_abstract,
                failed_sentences=len(failed_ids), rows=rows)

# ---------------------------------------------------------------- 화면 연결
def _u16(s, i):
    return len(s[:i].encode("utf-16-le")) // 2

PAPER_META = {
 "paper_a": dict(short="논문 A", title="Valorization of Brewer's Spent Grain Through Ultrasound-Assisted Extraction of Phenolic Compounds Using Deep Eutectic Solvents",
     authors="Paiva Santiago P, Fernandes FAN, de Santiago-Aguiar RS", journal="ACS Omega", year="2025", vol="10(22), 22603–22612",
     doi="10.1021/acsomega.4c10526", ko="맥주 찌꺼기에서 초음파와 심층공융용매(DES)로 페놀 성분을 추출", order="서론 → 방법 → 결과·논의 → 결론"),
 "paper_b": dict(short="논문 B", title="High-Temperature Hydrothermal Extraction of Phenolic Compounds from Brewer's Spent Grain and Malt Dust Biomass Using Natural Deep Eutectic Solvents",
     authors="Bleus D, Blockx H, Gesquiere E, Adriaensens P, Samyn P, Marchal W, Vandamme D", journal="Molecules", year="2024", vol="29(9), 1983",
     doi="10.3390/molecules29091983", ko="맥주 찌꺼기와 몰트 먼지에서 고온 수열 추출과 천연 심층공융용매(NADES)로 페놀 성분을 추출", order="서론 → 결과·논의 → 방법 → 결론"),
}

def build_viewer(runs, docs, out_path, template=None):
    """저장된 실행 결과로 '보고동사로 다시 읽기' 화면을 만든다. runs/docs는 [A] 또는 [A, B].
    부분 실행(소량 시험 등)은 분석한 문장만 결과를 표시하고, 나머지 문장은 '미분석'으로 표시한다."""
    if not 1 <= len(runs) == len(docs) <= 2: raise ValueError("실행 결과는 1개 또는 2개여야 합니다")
    template = template or os.path.join(HERE, "viewer_template.html")
    data = []
    for run, doc in zip(runs, docs):
        m = doc.by_id(); per = {s.id: [] for s in doc.sentences}
        for h in run["whole"]:
            s = m[h["sentence_id"]].text
            assert s[h["start"]:h["end"]] == h["text"], h
            per[h["sentence_id"]].append(dict(text=h["text"], start=_u16(s, h["start"]), end=_u16(s, h["end"]), role=h["role"], attr=h["attr"],
                agent=h.get("agent", ""), source=h["source"], lemma=h.get("lemma", ""), **({"at": h["agent_text"]} if h.get("agent_text") else {}),
                **({"n": h["note"]} if h.get("note") else {})))
        proc = run["record"].get("processing", {})
        failed = set(proc.get("failed_ids", []))
        requested = set(proc.get("requested_ids") or [s.id for s in doc.sentences])
        s_out = [dict(id=s.id, o=s.order, t=s.section_type, l=s.section_label, st=s.section_title, p=s.paragraph_id, w=s.word_count,
                      x=s.text, c=bool(citation_numbers(s.text)), f=s.id in failed, u=s.id not in requested,
                      hits=sorted(per[s.id], key=lambda h: h["start"])) for s in doc.sentences]
        rec = run["record"]
        data.append(dict(id=doc.document_id, meta=PAPER_META.get(doc.document_id, dict(short=doc.document_id, title=doc.document_id, authors="", journal="", year="", vol="", doi="", ko="", order="")),
                         run=dict(run_id=rec["run_id"], engine=rec["engine"], model=rec.get("model"), use_annotations=rec.get("use_annotations"),
                                  document_version=rec["document_version"], failed=len(failed),
                                  partial=len(requested) < len(doc.sentences), analyzed=len(requested - failed), total=len(doc.sentences)), s=s_out))
    t = open(template, encoding="utf-8").read()
    html = t.replace("__DATA__", json.dumps(data, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/"))
    if os.path.exists(out_path): raise FileExistsError(f"이미 있는 화면 파일은 덮어쓰지 않습니다: {out_path}")
    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
    open(out_path, "x", encoding="utf-8").write(html)
    return out_path
