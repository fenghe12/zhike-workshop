"""Convert OMML expressions into unambiguous text and localized reading cues."""
import unicodedata,re
from lxml import etree as E
M='http://schemas.openxmlformats.org/officeDocument/2006/math'
WORDS={
 'de':{'/':' geteilt durch ','=':' gleich ','+':' plus ','−':' minus ','*':' mal ','>':' größer als ','<':' kleiner als ','≥':' größer oder gleich ','≤':' kleiner oder gleich ','sub':' Index ','sup':' hoch ','sum':' Summe ','from':' von ','to':' bis ','hat':' Dach über '},
 'ja':{'/':' 割る ','=':' イコール ','+':' 足す ','−':' 引く ','*':' 掛ける ','>':' より大きい ','<':' より小さい ','≥':' 以上 ','≤':' 以下 ','sub':' 添字 ','sup':' のべき乗 ','sum':' 総和 ','from':' 範囲は ','to':' から ','hat':' ハット '},
 'zh':{'/':' 除以 ','=':' 等于 ','+':' 加 ','−':' 减 ','*':' 乘以 ','>':' 大于 ','<':' 小于 ','≥':' 大于等于 ','≤':' 小于等于 ','sub':' 下标 ','sup':' 的幂次为 ','sum':' 求和 ','from':' 从 ','to':' 到 ','hat':' 带帽的 '},
 'en':{'/':' divided by ','=':' equals ','+':' plus ','−':' minus ','*':' times ','>':' greater than ','<':' less than ','≥':' greater than or equal to ','≤':' less than or equal to ','sub':' subscript ','sup':' to the power ','sum':' sum ','from':' from ','to':' to ','hat':' hat '}}

def math_text(node,language=None):
    words=WORDS.get(language,WORDS['en'])
    def get(el,name):return el.find('{'+M+'}'+name)
    def walk(el):
        if el is None:return ''
        tag=E.QName(el).localname
        if tag.endswith('Pr'):return ''
        if tag=='t':return unicodedata.normalize('NFKC',el.text or '')
        if tag=='f':return '('+walk(get(el,'num'))+')'+(words['/'] if language else '/')+'('+walk(get(el,'den'))+')'
        if tag=='m':return '['+'; '.join(', '.join(walk(cell) for cell in row if E.QName(cell).localname=='e') for row in el if E.QName(row).localname=='mr')+']'
        if tag=='rad':return ('root_('+walk(get(el,'deg'))+')' if walk(get(el,'deg')) else 'sqrt')+'('+walk(get(el,'e'))+')'
        if tag in ['sSub','sSup','sSubSup']:
            out=walk(get(el,'e'))
            if get(el,'sub') is not None:out+=(words['sub'] if language else '_')+'('+walk(get(el,'sub'))+')'
            if get(el,'sup') is not None:out+=(words['sup'] if language else '^')+'('+walk(get(el,'sup'))+')'
            return out
        if tag=='acc':
            pr=get(el,'accPr');char=get(pr,'chr') if pr is not None else None
            mark=char.get('{'+M+'}val') if char is not None else '̂'
            names={'̂':'hat','̅':'overline','̄':'bar','̇':'dot','⃗':'vector'}
            if mark not in names:raise ValueError('unsupported math accent')
            return (words['hat'] if language and names[mark]=='hat' else names[mark])+'('+walk(get(el,'e'))+')' 
        if tag=='d':
            pr=get(el,'dPr');left=get(pr,'begChr') if pr is not None else None;right=get(pr,'endChr') if pr is not None else None
            return (left.get('{'+M+'}val') if left is not None else '(')+walk(get(el,'e'))+(right.get('{'+M+'}val') if right is not None else ')')
        if tag=='nary':
            pr=get(el,'naryPr');char=get(pr,'chr') if pr is not None else None
            symbol=char.get('{'+M+'}val') if char is not None else '∑'
            names={'∑':'sum','∫':'integral','∏':'product','⋂':'intersection','⋃':'union'}
            if symbol not in names:raise ValueError('unsupported n-ary math operator')
            name=words['sum'] if language and symbol=='∑' else names[symbol]
            return (name+words['from'] if language else name+'_(')+walk(get(el,'sub'))+(words['to'] if language else ')^(')+walk(get(el,'sup'))+(' ' if language else ') ')+walk(get(el,'e'))
        if tag=='eqArr':return '; '.join(walk(c) for c in el if not E.QName(c).localname.endswith('Pr'))
        return ''.join(walk(c) for c in el)
    text=walk(node)
    if language:
        for token in ['≥','≤','>','<','=','+','−','*']:text=text.replace(token,words[token])
        text=text.replace('σ',' sigma ' if language in ['de','en'] else (' シグマ ' if language=='ja' else ' 西格玛 '))
    return re.sub(r'\s+',' ',text).strip()
