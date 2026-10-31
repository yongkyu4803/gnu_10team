"""
추출 검증 그림: extract_pdf.py가 잡은 초록·절 제목·절별 본문 줄을 PDF 쪽 그림 위에 색 상자로 그린다.
사용: python3 scripts/render_layout.py <PDF 폴더> <1_extract 폴더> <출력 폴더> [--dpi 45] [--cols 4]
입력: <id>.pdf + <id>_layout.json(extract_pdf.py가 만듦). 출력: <id>.png(모든 쪽을 한 장에), index.html(모아 보기)
색: 초록 노랑 테두리, 절 제목 빨강 테두리, 서론 파랑, 실험·방법 초록, 결과·논의 주황, 결론 보라, 세지 않은 본문 크기 줄 회색 테두리.
그림은 사람이 보는 확인용이다. 세는 값에는 영향이 없다.
"""
import sys, os, json, glob, argparse, html
import pdfplumber
from PIL import Image, ImageDraw, ImageFont

COLORS = {'INT': (40, 110, 230), 'MET': (30, 160, 70), 'RD': (240, 140, 20), 'RES': (240, 140, 20), 'DIS': (220, 90, 30),
          'CON': (150, 60, 200), 'OTHER': (120, 120, 120)}
LABEL = {'INT': '서론', 'MET': '실험·방법', 'RD': '결과·논의', 'RES': '결과', 'DIS': '논의', 'CON': '결론'}

def font(size):
    for p in ('C:/Windows/Fonts/malgun.ttf', '/System/Library/Fonts/AppleSDGothicNeo.ttc', '/usr/share/fonts/truetype/nanum/NanumGothic.ttf'):
        if os.path.exists(p): return ImageFont.truetype(p, size)
    return ImageFont.load_default()

def render(pdf_path, layout, dpi, cols):
    lh = layout['body_size'] * 1.15
    pages = []
    with pdfplumber.open(pdf_path) as pdf:
        for pi, page in enumerate(pdf.pages):
            img = page.to_image(resolution=dpi).original.convert('RGB')
            sc = img.width / float(page.width)
            ov = Image.new('RGBA', img.size, (0, 0, 0, 0)); d = ImageDraw.Draw(ov)
            for l in layout['lines']:
                if l['page'] != pi: continue
                r = [l['x0'] * sc, l['top'] * sc, l['x1'] * sc, (l['top'] + lh) * sc]
                if l['kind'] == 'head' and l['sec'] not in ('TOP',):
                    d.rectangle(r, outline=(220, 0, 0, 255), width=3)
                elif l['used']:
                    c = COLORS.get(l['sec'], COLORS['OTHER']); d.rectangle(r, fill=c + (90,))
                elif l['kind'] in ('body', 'body_small'):
                    d.rectangle(r, outline=(130, 130, 130, 200), width=1)
            if pi == 0 and layout.get('abstract_box'):
                x0, t, x1, b = layout['abstract_box']; d.rectangle([x0 * sc - 2, t * sc - 2, x1 * sc + 2, b * sc + 2], outline=(230, 190, 0, 255), width=4)
            img = Image.alpha_composite(img.convert('RGBA'), ov).convert('RGB')
            ImageDraw.Draw(img).text((6, 4), f'p{pi + 1}', fill=(0, 0, 0), font=font(16))
            pages.append(img)
    w, h = max(p.width for p in pages), max(p.height for p in pages)
    rows = (len(pages) + cols - 1) // cols
    head_h = 70
    sheet = Image.new('RGB', (cols * (w + 8) + 8, head_h + rows * (h + 8) + 8), 'white')
    dr = ImageDraw.Draw(sheet)
    dr.text((10, 8), f"{layout['document_id']}  ({layout['extractor']}, 본문 {layout['body_size']} pt)", fill=(0, 0, 0), font=font(20))
    x = 10
    for k, name in (('ABS', '초록'), ('HEAD', '절 제목'), ('INT', '서론'), ('MET', '실험·방법'), ('RD', '결과·논의'), ('CON', '결론'), ('SKIP', '세지 않은 줄')):
        if k == 'ABS': dr.rectangle([x, 42, x + 22, 58], outline=(230, 190, 0), width=3)
        elif k == 'HEAD': dr.rectangle([x, 42, x + 22, 58], outline=(220, 0, 0), width=3)
        elif k == 'SKIP': dr.rectangle([x, 42, x + 22, 58], outline=(130, 130, 130), width=1)
        else: dr.rectangle([x, 42, x + 22, 58], fill=tuple(min(255, int(c * .45 + 255 * .55)) for c in COLORS[k]))
        dr.text((x + 28, 40), name, fill=(0, 0, 0), font=font(15)); x += 40 + 16 * len(name)
    for i, p in enumerate(pages):
        sheet.paste(p, (8 + (i % cols) * (w + 8), head_h + 8 + (i // cols) * (h + 8)))
    return sheet

def main():
    ap = argparse.ArgumentParser(); ap.add_argument('pdf_dir'); ap.add_argument('extract_dir'); ap.add_argument('out_dir')
    ap.add_argument('--dpi', type=int, default=45); ap.add_argument('--cols', type=int, default=4)
    a = ap.parse_args(); os.makedirs(a.out_dir, exist_ok=True)
    done = []
    for lj in sorted(glob.glob(os.path.join(a.extract_dir, '*_layout.json'))):
        layout = json.load(open(lj, encoding='utf-8')); did = layout['document_id']
        pdf = os.path.join(a.pdf_dir, did + '.pdf')
        if not os.path.exists(pdf): print(f'PDF 없음: {pdf}'); continue
        render(pdf, layout, a.dpi, a.cols).save(os.path.join(a.out_dir, did + '.png'), optimize=True)
        rep = os.path.join(a.extract_dir, did + '_report.json')
        st = json.load(open(rep, encoding='utf-8'))['stats'] if os.path.exists(rep) else {}
        done.append((did, st)); print('그림', did)
    rows = ''.join(f"<h2>{html.escape(d)}</h2><p>절별 문장 수: {html.escape(json.dumps(st.get('by_section', {}), ensure_ascii=False))} · "
                   f"인용 번호 회수 {st.get('cited_in_list', '?')}/{st.get('refs_in_list', '?')}</p><img src='{html.escape(d)}.png'>" for d, st in done)
    open(os.path.join(a.out_dir, 'index.html'), 'w', encoding='utf-8').write(
        "<!doctype html><html lang='ko'><head><meta charset='utf-8'><title>추출 검증 그림</title><style>body{font-family:'Malgun Gothic',sans-serif;margin:16px}"
        "img{max-width:100%;border:1px solid #ccc}h2{margin-top:28px}</style></head><body><h1>추출 검증 그림</h1>"
        "<p>노랑 테두리 초록, 빨강 테두리 절 제목, 파랑 서론, 초록 실험·방법, 주황 결과·논의, 보라 결론, 회색 테두리 세지 않은 줄.</p>" + rows + "</body></html>")

if __name__ == '__main__':
    main()
