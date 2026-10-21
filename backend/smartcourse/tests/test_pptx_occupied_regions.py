import tempfile
import unittest
import zipfile
from pathlib import Path
from agents.ppt_renderer import occupied_regions

A='http://schemas.openxmlformats.org/drawingml/2006/main'
P='http://schemas.openxmlformats.org/presentationml/2006/main'
R='http://schemas.openxmlformats.org/officeDocument/2006/relationships'
PKG='http://schemas.openxmlformats.org/package/2006/relationships'
MC='http://schemas.openxmlformats.org/markup-compatibility/2006'


def shape(identifier,text,x,y,w,h):
    return f'<p:sp><p:nvSpPr><p:cNvPr id="{identifier}" name="Text"/><p:nvPr/></p:nvSpPr><p:spPr><a:xfrm><a:off x="{x}" y="{y}"/><a:ext cx="{w}" cy="{h}"/></a:xfrm></p:spPr><p:txBody><a:p><a:r><a:t>{text}</a:t></a:r></a:p></p:txBody></p:sp>'


class OccupiedRegionTests(unittest.TestCase):
    def test_alternate_content_and_master_footer_are_occupied(self):
        attrs=f'xmlns:p="{P}" xmlns:a="{A}" xmlns:r="{R}" xmlns:mc="{MC}"'
        data={
            'ppt/presentation.xml':f'<p:presentation {attrs}><p:sldIdLst><p:sldId id="1" r:id="r1"/></p:sldIdLst><p:sldSz cx="1000" cy="600"/></p:presentation>',
            'ppt/_rels/presentation.xml.rels':f'<Relationships xmlns="{PKG}"><Relationship Id="r1" Target="slides/slide1.xml"/></Relationships>',
            'ppt/slides/slide1.xml':f'<p:sld {attrs}><p:cSld><p:spTree><mc:AlternateContent><mc:Choice>{shape(2,"Formula",100,400,600,100)}</mc:Choice><mc:Fallback/></mc:AlternateContent></p:spTree></p:cSld></p:sld>',
            'ppt/slides/_rels/slide1.xml.rels':f'<Relationships xmlns="{PKG}"><Relationship Type="{R}/slideLayout" Target="../slideLayouts/slideLayout1.xml"/></Relationships>',
            'ppt/slideLayouts/slideLayout1.xml':f'<p:sldLayout {attrs}/>',
            'ppt/slideLayouts/_rels/slideLayout1.xml.rels':f'<Relationships xmlns="{PKG}"><Relationship Type="{R}/slideMaster" Target="../slideMasters/slideMaster1.xml"/></Relationships>',
            'ppt/slideMasters/slideMaster1.xml':f'<p:sldMaster {attrs}><p:cSld><p:spTree>{shape(3,"Footer",50,560,850,20)}</p:spTree></p:cSld></p:sldMaster>',
        }
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'course.pptx'
            with zipfile.ZipFile(path,'w') as archive:
                for name,text in data.items():archive.writestr(name,text)
            regions=occupied_regions(path,1000)[0]
            self.assertIn((100,400,700,500),regions)
            self.assertIn((50,560,900,580),regions)


if __name__=='__main__':unittest.main()
