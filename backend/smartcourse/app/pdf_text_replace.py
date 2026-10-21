"""Replace verified text regions while retaining PDF images and vector artwork."""
import re
from pathlib import Path


def replace_pdf_text_regions(source, destination, regions, font_file):
    import pymupdf
    source, destination = Path(source), Path(destination)
    if source.resolve() == destination.resolve():
        raise ValueError('PDF 翻译必须写入新文件')
    font = pymupdf.Font(fontfile=str(font_file))
    with pymupdf.open(source) as document:
        checked = []
        for region in regions:
            number = region['page']
            if isinstance(number, bool) or not isinstance(number, int) or not 1 <= number <= len(document):
                raise ValueError('PDF 页面编号无效')
            page = document[number-1]
            rect = pymupdf.Rect(region['bbox'])
            bounds = pymupdf.Rect(0, 0, page.cropbox.width, page.cropbox.height)
            if rect.is_empty or rect.is_infinite or not bounds.contains(rect):
                raise ValueError('文字区域超出原页面')
            actual = page.get_textbox(rect)
            normalize = lambda value: re.sub(r'\s+', '', value)
            if not region['sourceText'].strip() or normalize(actual) != normalize(region['sourceText']):
                raise ValueError('PDF 区域文字与待翻译原文不一致')
            translated = region['translatedText']
            if not isinstance(translated, str) or not translated.strip():
                raise ValueError('PDF 译文为空')
            if any(not font.has_glyph(ord(character)) for character in translated if not character.isspace()):
                raise ValueError('所选字体不覆盖 PDF 译文字符')
            if any(prior_number == number and rect.intersects(prior_rect) for prior_number, prior_rect, _ in checked):
                raise ValueError('PDF 翻译区域相互重叠')
            checked.append((number, rect, region))
        for number in sorted({item[0] for item in checked}):
            page = document[number-1]
            selections = [(rect, region) for current, rect, region in checked if current == number]
            for rect, _ in selections:
                page.add_redact_annot(rect, fill=False, cross_out=False)
            page.apply_redactions(images=0, graphics=0, text=0)
            for rect, region in selections:
                size = float(region['fontSize'])
                minimum = max(7, size*.42)
                translated_text = '\n'.join(line.strip() for line in region['translatedText'].splitlines() if line.strip())
                shallow_line = rect.height <= 16 or (size <= 20 and rect.height <= size*1.1)
                original_line_count=len([line for line in region['sourceText'].splitlines() if line.strip()])
                if shallow_line:
                    translated_text = re.sub(r'\s+', ' ', translated_text).strip()
                single_line=(original_line_count==1 and '\n' not in translated_text)
                if (region.get('origin') and '\n' not in translated_text) or shallow_line or single_line:
                    while size >= minimum and font.text_length(translated_text, fontsize=size) > rect.width:
                        size -= .5
                    if size < minimum:
                        candidate = pymupdf.Rect(max(0,rect.x0-rect.width),rect.y0,
                                                 min(page.cropbox.width,rect.x1+rect.width),rect.y1)
                        other_rects=[other for other,_ in selections if other!=rect]
                        if any(candidate.intersects(other) for other in other_rects):
                            raise ValueError(f"PDF 第 {number} 页译文超出原行宽：{region['sourceText'][:80]}")
                        size=float(region['fontSize'])
                        while size>=7 and font.text_length(translated_text,fontsize=size)>candidate.width:
                            size-=.5
                        if size<7:raise ValueError(f"PDF 第 {number} 页译文超出原行宽：{region['sourceText'][:80]}")
                        rect=candidate
                    origin = region.get('origin') or (rect.x0, rect.y1-max(.5,size*.08))
                    page.insert_text(origin, translated_text, fontname='moocTranslation',
                        fontfile=str(font_file), fontsize=size, color=tuple(region.get('color',(0,0,0))))
                    continue
                insert_rect = rect
                if size >= 28:
                    candidate = pymupdf.Rect(max(0, rect.x0-rect.width*.75), max(0, rect.y0-size*.15),
                                             min(page.cropbox.width, rect.x1+rect.width*.75),
                                             min(page.cropbox.height, rect.y1+size*.35))
                    other_rects = [other for other, _ in selections if other != rect]
                    if not any(candidate.intersects(other) for other in other_rects):
                        insert_rect = candidate
                while size >= minimum:
                    spare = page.insert_textbox(insert_rect, translated_text, fontname='moocTranslation',
                        fontfile=str(font_file), fontsize=size, color=tuple(region.get('color', (0, 0, 0))))
                    if spare >= 0:
                        break
                    size -= .5
                else:
                    raise ValueError(f"PDF 第 {number} 页译文无法放入原文字区域：{region['sourceText'][:80]}")
        destination.parent.mkdir(parents=True, exist_ok=True)
        pending = destination.with_suffix('.pending.pdf')
        document.save(pending, garbage=4, deflate=True)
        pending.replace(destination)
    return {'replacedRegions': len(checked), 'output': str(destination)}
