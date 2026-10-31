"""
Stage 1 한 번에 실행: PDF 묶음(2~10편) → 본문 추출 → 추출 품질 검사 → 섹션별 동사·헷지 기준선
사용: python scripts/run_stage1.py <PDF 폴더> <출력 폴더> [--model en_core_web_sm]   (Python 3.12 권장, Windows는 py -3.12)
품질 기준을 넘지 못한 논문은 기준선에서 빼고 이유를 남긴다(--keep-all이면 넣고 경고만).
"""
import sys, os, glob, json, argparse, shutil, subprocess
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
import extract_pdf

GATE_CITE = 0.95    # 참고문헌 번호 가운데 본문 인용으로 복원된 비율
GATE_OPEN = 0.05    # 끝이 열린(문장부호로 끝나지 않은) 문장 비율

def check_env(model):
    """실행 첫머리 환경 점검: 한국어 Windows(cp949) 콘솔, spaCy 모델, pdftotext 종류(xpdf면 참고문헌 수가 틀린다)"""
    for s in (sys.stdout, sys.stderr):
        try: s.reconfigure(encoding='utf-8')
        except (AttributeError, ValueError): pass
    try:
        import spacy; spacy.load(model)
    except Exception as e:
        sys.exit(f'spaCy 또는 모델 {model}을 불러오지 못했습니다({type(e).__name__}: {e}). '
                 f'Python 3.12에서 pip install -r requirements.txt, python -m spacy download {model}을 실행하세요. 지금 Python {sys.version.split()[0]}')
    try:
        v = subprocess.run(['pdftotext', '-v'], capture_output=True, text=True, encoding='utf-8', errors='replace')
        ver = (v.stdout + v.stderr).strip().splitlines()[0] if (v.stdout + v.stderr).strip() else '?'
        if 'Glyph & Cog' in v.stdout + v.stderr and 'poppler' not in (v.stdout + v.stderr).lower():
            sys.exit(f'PATH에서 xpdf의 pdftotext가 먼저 잡힙니다({ver}). xpdf는 저자 수·참고문헌 수를 틀리게 냅니다. poppler의 bin 폴더를 PATH 맨 앞에 두세요.')
        print(f'환경: Python {sys.version.split()[0]}, {ver}')
    except FileNotFoundError:
        print(f'환경: Python {sys.version.split()[0]}, pdftotext 없음(참고문헌 수를 pdfplumber로 셉니다)')

def main():
    ap = argparse.ArgumentParser(); ap.add_argument('pdf_dir'); ap.add_argument('out_dir')
    ap.add_argument('--model', default='en_core_web_sm'); ap.add_argument('--keep-all', action='store_true')
    a = ap.parse_args()
    check_env(a.model)
    pdfs = sorted(glob.glob(os.path.join(a.pdf_dir, '*.pdf')))
    if not 2 <= len(pdfs) <= 10: sys.exit(f'PDF는 2~10편이어야 합니다(지금 {len(pdfs)}편).')
    ex, ok_dir = os.path.join(a.out_dir, '1_extract'), os.path.join(a.out_dir, '1_extract_passed')
    os.makedirs(ex, exist_ok=True); os.makedirs(ok_dir, exist_ok=True)
    gate = []
    for p in pdfs:
        did = os.path.splitext(os.path.basename(p))[0]
        st = extract_pdf.main(p, did, ex)
        cite = st['cited_in_list'] / st['refs_in_list'] if st['refs_in_list'] else 0
        open_ = len(st['no_terminal_punct']) / max(1, st['sentences'])
        passed = cite >= GATE_CITE and open_ <= GATE_OPEN and not st['leaks'] and st['sentences'] > 0
        gate.append(dict(document_id=did, sentences=st['sentences'], cite_recovery=round(cite, 3), open_sentences=round(open_, 3),
                         leaks=len(st['leaks']), review_items=st['review_items'], result='Pass' if passed else 'Fail'))
        if passed or a.keep_all:
            for suf in ('_input.txt', '_structure.tsv'): shutil.copy(os.path.join(ex, did + suf), ok_dir)
    json.dump(gate, open(os.path.join(a.out_dir, 'extract_gate.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    for g in gate: print(f"{g['result']}  {g['document_id']}: 문장 {g['sentences']}, 인용 회수 {g['cite_recovery']:.0%}, 끝이 열린 문장 {g['open_sentences']:.1%}, 확인 목록 {g['review_items']}건")
    r = subprocess.run([sys.executable, os.path.join(HERE, 'hedge_baseline.py'), ok_dir, os.path.join(a.out_dir, '2_baseline'), '--model', a.model],
                       env=dict(os.environ, PYTHONUTF8='1'))   # 하위 프로세스도 UTF-8(python -X utf8과 같음)
    sys.exit(r.returncode)

if __name__ == '__main__':
    main()
