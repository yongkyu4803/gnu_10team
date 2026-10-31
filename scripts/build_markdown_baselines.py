"""Build Stage 1 baselines using existing Markdown, never re-read source PDFs."""
import csv, hashlib, html, json, re, subprocess, sys
from pathlib import Path
from datetime import datetime, timezone
ROOT=Path(__file__).resolve().parents[1]
SCRIPTS=ROOT/'section-verb-hedge-baseline'/'scripts'
sys.path.insert(0,str(SCRIPTS))
import extract_pdf
GROUPS=['CM','IC','JOC','JPC_C']
OUT=ROOT/'baselines_markdown'
PATTERNS=[('INT',r'introduction|background'),('RD',r'results?\s*(?:and|&)\s*discussion|discussion\s*(?:and|&)\s*results?'),('RES',r'results?'),('DIS',r'discussion'),('MET',r'experimental(?:\s+(?:section|details|methods|procedures?))?|materials\s*(?:and|&)\s*methods|methods|computational\s+(?:details|methods|section)|theoretical\s+(?:methods|details)'),('CON',r'conclusions?|concluding\s+remarks|summary\s*(?:and|&)\s*conclusions?'),('BACK',r'references(?:\s+and\s+notes)?|notes\s+and\s+references|acknowledg(?:e)?ments?|associated\s+content|supporting\s+information|author\s+information')]
def heading(line):
 text=re.sub(r'^\s*#{1,6}\s*','',line).replace('**','').strip()
 text=re.sub(r'^[■▪’\s]+','',text)
 text=re.sub(r'^(?:[IVX]+|\d+(?:\.\d+)*)[.)]?\s+','',text)
 if text and text[0].islower():return None
 for sec,pat in PATTERNS:
  m=re.match(r'^(?:'+pat+r')(?:\s*[.:]\s*|\t+|\s*$)',text,re.I)
  if m:return sec,text[m.end():].strip()
 return None

def prepare(group, source_dir=None, output_dir=None, documents=None, min_words=1000):
 out=Path(output_dir) if output_dir is not None else OUT/group;inp=out/'1_markdown_input';inp.mkdir(parents=True,exist_ok=True)
 audits=[]
 source=Path(source_dir) if source_dir is not None else ROOT/group
 for path in sorted(source.glob('*.md')):
  if documents is not None and path.name not in documents:continue
  raw=path.read_text(encoding='utf-8')
  normalized=[]
  for line in raw.replace('\\t','\t').splitlines():
   if heading(line):normalized.append('')
   normalized.append(line)
  parts=re.split(r'\n\s*\n','\n'.join(normalized))
  # First block is kordoc metadata, document outline and converter warnings.
  if parts and parts[0].startswith('[포맷:'):parts=parts[1:]
  sec=None;sections={};heads=[];skipped=0;nonprose=0;unexpected=[];last_rank=0;invalid_ranges=[]
  for part in parts:
   part=part.strip()
   if not part:continue
   h=heading(part)
   if h:
    sec,part=h;heads.append(sec)
    rank={'INT':1,'MET':2,'RES':3,'DIS':3,'RD':3,'CON':4,'BACK':5}[sec]
    if rank<last_rank and sec!='MET':unexpected.append(sec)
    last_rank=max(last_rank,rank)
    if not part:continue
   if sec is None or sec=='BACK':skipped+=1;continue
   if re.match(r'^(?:#{1,6}\s*)?(?:Downloaded from|pubs\.acs\.org|(?:Figure|Fig\.|Scheme|Chart|Table)\s*\d|\(\d+\)|\[\d+\]\s)',part,re.I):skipped+=1;continue
   if part.startswith('|') or part.startswith('<table') or part.startswith('!['):skipped+=1;continue
   # Drop running page/author headings, but keep scientific subsection content.
   if re.search(r'\b(?:J\. Org\. Chem\.|Inorg\. Chem\.|Chem\. Mater\.|J\. Phys\. Chem\.)',part) and len(part)<150:skipped+=1;continue
   if re.match(r'^#{1,6}\s+',part):
    if len(part.split())<12:skipped+=1;continue
    part=re.sub(r'^#{1,6}\s*','',part)
   def superscript(m):
    b=re.sub('<[^>]*>','',m[1]).strip()
    pre=part[:m.start()];following=part[m.end():m.end()+1]
    word=re.search(r'(\S+)$',pre)
    unit=bool(word and re.fullmatch(r'(?:cm|mm|nm|μm|m|s|h|K|M|mol|L|g|kg|kJ|kcal|eV|Hz|MHz)',word[1]))
    allowed=bool(pre and not pre[-1].isspace() and not pre[-1].isdigit() and not unit and not (following and following.isalpha()))
    return '['+b+']' if allowed and re.fullmatch(r'[1-9]\d{0,2}[a-h]?(?:\s*[,−–-]\s*(?:\d{1,3}[a-h]?|[a-h]))*',b) else b
   part=re.sub(r'<sup>(.*?)</sup>',superscript,part,flags=re.S|re.I)
   part=re.sub(r'<[^>]+>','',part)
   part=re.sub(r'\[([^\]]+)\]\(https?://[^)]+\)',r'\1',part)
   part=html.unescape(part).replace('\\*','*').replace('**','').replace('\u00ad','')
   def numeric_bracket(m):
    ranges=re.findall(r'(\d+)\s*[−–-]\s*(\d+)',m[1])
    if any(int(b)<int(a) or int(b)-int(a)>200 for a,b in ranges):
     invalid_ranges.append(m[0]);return '('+m[1]+')'
    return m[0]
   part=re.sub(r'\[([1-9][\d,\s−–-]*)\]',numeric_bracket,part)
   part=re.sub(r'\s+',' ',part).strip()
   if part:sections.setdefault(sec,[]).append(part)
  rows=[];lines=[f'# document_id: {path.stem}','# extractor: kordoc-markdown-adapter-1'];order=0
  for si,(section,paras) in enumerate(sections.items(),1):
   sequence=0
   for pi,para in enumerate(paras,1):
    for j,sentence in enumerate(extract_pdf.split_sents(para),1):
     order+=1;sequence+=1;sid=f'{si}-{sequence:03d}';prose=not bool(extract_pdf.NONPROSE.search(sentence));nonprose+=not prose
     lines.append(sid+'\t'+sentence.replace('\t',' '))
     rows.append(dict(document_id=path.stem,sentence_id=sid,order=order,section_type=section,section_label=section,section_title=section,paragraph_id=f'{si}-{pi}',sentence_in_paragraph=j,word_count=len(sentence.split()),prose=str(prose).lower()))
  reasons=[]
  if not sections.get('INT'):reasons.append('서론 헤딩/본문 미인식')
  if not any(sections.get(k) for k in ('RD','RES','DIS')):reasons.append('결과·논의 헤딩/본문 미인식')
  if unexpected:reasons.append('섹션 순서 이상: '+','.join(unexpected))
  if sum(len(r.split()) for paras in sections.values() for r in paras)<min_words:reasons.append(f'정리된 본문 {min_words:,}단어 미만')
  audit=dict(document_id=path.stem,source=group+'/'+path.name,sha256=hashlib.sha256(raw.encode()).hexdigest(),result='Fail' if reasons else 'Pass',reasons=reasons,headings=heads,section_words={s:sum(len(p.split()) for p in ps) for s,ps in sections.items()},sentences=len(rows),nonprose=nonprose,skipped_blocks=skipped,source_converter_warnings=[l for l in raw.splitlines() if l.startswith('- [p')],noncitation_numeric_ranges=invalid_ranges,pdf_quality_gate='not_applicable_markdown_input')
  audits.append(audit)
  if not reasons:
   (inp/(path.stem+'_input.txt')).write_text('\n'.join(lines)+'\n',encoding='utf-8')
   with (inp/(path.stem+'_structure.tsv')).open('w',encoding='utf-8',newline='') as f:
    w=csv.DictWriter(f,fieldnames=list(rows[0]),delimiter='\t');w.writeheader();w.writerows(rows)
 (out/'markdown_gate.json').write_text(json.dumps(audits,ensure_ascii=False,indent=2),encoding='utf-8')
 print(group,'Pass',sum(a['result']=='Pass' for a in audits),'Fail',sum(a['result']=='Fail' for a in audits),flush=True)
 return audits

if __name__=='__main__':
 for group in GROUPS:prepare(group)
