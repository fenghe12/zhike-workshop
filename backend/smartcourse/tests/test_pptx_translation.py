import json
import tempfile
import unittest
import zipfile
from pathlib import Path

from app.pptx_translation import translate_package


def presentation_parts(package, count=1):
    ids = ''.join(f'<p:sldId id="{256+i}" r:id="rId{i}"/>' for i in range(1, count+1))
    package.writestr('ppt/presentation.xml', '<p:presentation xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><p:sldIdLst>'+ids+'</p:sldIdLst></p:presentation>')
    relations = ''.join(f'<Relationship Id="rId{i}" Target="slides/slide{i}.xml"/>' for i in range(1, count+1))
    package.writestr('ppt/_rels/presentation.xml.rels', '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'+relations+'</Relationships>')


class TranslationPackageTests(unittest.TestCase):
    def test_plain_master_heading_is_translated_as_one_phrase(self):
        from lxml import etree as E
        class Translator:
            def respond_json(self, prompt, **kwargs):
                values = json.loads(prompt.split('\n', 1)[1])
                self.asserted_input = values
                return {'paragraphs': [['1 AI 개요']]}
        with tempfile.TemporaryDirectory() as temporary:
            source, output = Path(temporary)/'source.pptx', Path(temporary)/'output.pptx'
            runs = ''.join('<a:r><a:rPr b="1"/><a:t>'+value+'</a:t></a:r>' for value in ['1',' ','Overview',' ','of',' ','AI'])
            master = '<p:sldMaster xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main" xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main"><p:sp><a:p>'+runs+'</a:p></p:sp></p:sldMaster>'
            with zipfile.ZipFile(source,'w') as package:
                presentation_parts(package)
                package.writestr('ppt/slides/slide1.xml','<root/>')
                package.writestr('ppt/slides/_rels/slide1.xml.rels','<Relationships><Relationship Target="../slideLayouts/slideLayout1.xml"/></Relationships>')
                package.writestr('ppt/slideLayouts/slideLayout1.xml','<root/>')
                package.writestr('ppt/slideLayouts/_rels/slideLayout1.xml.rels','<Relationships><Relationship Target="../slideMasters/slideMaster1.xml"/></Relationships>')
                package.writestr('ppt/slideMasters/slideMaster1.xml',master)
            translator = Translator()
            translate_package(source,output,translator,'Korean')
            self.assertEqual(translator.asserted_input[0]['runs'], ['1 Overview of AI'])
            with zipfile.ZipFile(output) as package:
                tree = E.fromstring(package.read('ppt/slideMasters/slideMaster1.xml'))
                nodes = list(tree.iter('{http://schemas.openxmlformats.org/drawingml/2006/main}t'))
                self.assertEqual(''.join(node.text or '' for node in nodes),'1 AI 개요')
                self.assertEqual(len(nodes),7)
                self.assertTrue(all(node.get('b')=='1' for node in tree.iter('{http://schemas.openxmlformats.org/drawingml/2006/main}rPr')))

    def test_protected_personal_name_can_remain_in_source_script(self):
        class Translator:
            def respond_json(self, *args, **kwargs):
                return {'paragraphs': [['潘梓正, Software Engineering']]}
        with tempfile.TemporaryDirectory() as temporary:
            source, output = Path(temporary)/'input.pptx', Path(temporary)/'output.pptx'
            with zipfile.ZipFile(source, 'w') as package:
                presentation_parts(package)
                package.writestr('ppt/slides/slide1.xml', '<a:p xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main"><a:r><a:t>潘梓正，软件工程</a:t></a:r></a:p>')
            translate_package(source, output, Translator(), 'English', protected_names=['潘梓正'])
            with zipfile.ZipFile(output) as package:
                self.assertIn('潘梓正', package.read('ppt/slides/slide1.xml').decode())

    def test_source_language_residue_is_retried(self):
        class Translator:
            calls = 0
            def respond_json(self, *args, **kwargs):
                self.calls += 1
                text = 'Perzeptron实现了二分类' if self.calls == 1 else 'Das Perzeptron klassifiziert zwei Klassen.'
                return {'paragraphs': [[text]]}
        with tempfile.TemporaryDirectory() as temporary:
            source, output = Path(temporary)/'input.pptx', Path(temporary)/'output.pptx'
            with zipfile.ZipFile(source, 'w') as package:
                presentation_parts(package)
                package.writestr('ppt/slides/slide1.xml', '<a:p xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main"><a:r><a:t>感知机实现二分类</a:t></a:r></a:p>')
            translator = Translator()
            translate_package(source, output, translator, 'German')
            self.assertEqual(translator.calls, 2)
            with zipfile.ZipFile(output) as package:
                text = package.read('ppt/slides/slide1.xml').decode()
                self.assertIn('Das Perzeptron', text)
                self.assertNotIn('实现', text)

    def test_unselected_slide_is_not_translated(self):
        class Translator:
            calls = 0
            def respond_json(self, *args, **kwargs):
                self.calls += 1
                return {'paragraphs': [['Translated']]}
        with tempfile.TemporaryDirectory() as temporary:
            source, output = Path(temporary)/'input.pptx', Path(temporary)/'output.pptx'
            xml = b'<a:p xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main"><a:r><a:t>Original</a:t></a:r></a:p>'
            with zipfile.ZipFile(source, 'w') as package:
                presentation_parts(package)
                package.writestr('ppt/slides/slide1.xml', xml)
                package.writestr('ppt/slides/slide2.xml', xml)
            translator = Translator()
            translate_package(source, output, translator, 'German')
            self.assertEqual(translator.calls, 1)
            with zipfile.ZipFile(output) as package:
                self.assertEqual(package.read('ppt/slides/slide2.xml'), xml)

    def test_resume_keeps_completed_batches(self):
        class InterruptedGateway:
            calls = 0
            def respond_json(self, prompt, **kwargs):
                self.calls += 1
                if self.calls > 1:
                    raise ConnectionError("Temporary interruption")
                return {"paragraphs": [["Erste Seite"]]}
        class ResumedGateway:
            calls = 0
            def respond_json(self, prompt, **kwargs):
                self.calls += 1
                return {"paragraphs": [["Zweite Seite"]]}
        with tempfile.TemporaryDirectory() as temporary:
            source, output = Path(temporary)/"input.pptx", Path(temporary)/"out.pptx"
            with zipfile.ZipFile(source, "w") as package:
                presentation_parts(package, 2)
                for index in [1,2]:
                    package.writestr(f"ppt/slides/slide{index}.xml", f'<a:p xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main"><a:r><a:t>Page {index}</a:t></a:r></a:p>')
            with self.assertRaises(ConnectionError):
                translate_package(source, output, InterruptedGateway(), "German")
            resumed = ResumedGateway()
            translate_package(source, output, resumed, "German")
            self.assertEqual(resumed.calls, 1)
            with zipfile.ZipFile(output) as package:
                self.assertIn(b"Erste Seite", package.read("ppt/slides/slide1.xml"))
                self.assertIn(b"Zweite Seite", package.read("ppt/slides/slide2.xml"))

    def test_formats_math_and_binary_parts_survive(self):
        from lxml import etree as E
        xml = b'''<root xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main"
            xmlns:m="http://schemas.openxmlformats.org/officeDocument/2006/math"
            xmlns:mc="http://schemas.openxmlformats.org/markup-compatibility/2006">
            <a:p><a:r><a:rPr b="1"/><a:t>Course</a:t></a:r><a:r><a:t> title</a:t></a:r></a:p>
            <mc:AlternateContent><mc:Choice Requires="a"><m:oMath><m:r><m:t>x=2</m:t></m:r></m:oMath></mc:Choice>
            <mc:Fallback><a:blip/></mc:Fallback></mc:AlternateContent></root>'''
        class Translator:
            def respond_json(self, prompt, **kwargs):
                values = json.loads(prompt.split('\n', 1)[1])
                return {"paragraphs": [[value + " translated" for value in item["runs"]] for item in values]}
        with tempfile.TemporaryDirectory() as temporary:
            source, output = Path(temporary) / "input.pptx", Path(temporary) / "out.pptx"
            parts = ["ppt/slides/slide1.xml", "ppt/slideMasters/slideMaster1.xml", "ppt/slideLayouts/slideLayout1.xml"]
            with zipfile.ZipFile(source, "w") as package:
                presentation_parts(package)
                for part in parts:
                    package.writestr(part, xml)
                package.writestr('ppt/slides/_rels/slide1.xml.rels', '<Relationships><Relationship Target="../slideLayouts/slideLayout1.xml"/></Relationships>')
                package.writestr('ppt/slideLayouts/_rels/slideLayout1.xml.rels', '<Relationships><Relationship Target="../slideMasters/slideMaster1.xml"/></Relationships>')
                package.writestr("ppt/media/image1.bin", b"original image bytes")
            result = translate_package(source, output, Translator(), "German")
            self.assertEqual(result["translatedTextNodes"], 6)
            self.assertEqual(result["fallbackImagesRequiringRefresh"], 3)
            with zipfile.ZipFile(output) as package:
                self.assertEqual(package.read("ppt/media/image1.bin"), b"original image bytes")
                for part in parts:
                    tree = E.fromstring(package.read(part))
                    self.assertEqual(tree.find('.//{http://schemas.openxmlformats.org/officeDocument/2006/math}t').text, "x=2")
                    self.assertEqual(tree.find('.//{http://schemas.openxmlformats.org/drawingml/2006/main}rPr').get('b'), "1")
                    self.assertEqual(tree.find('.//{http://schemas.openxmlformats.org/drawingml/2006/main}t').text, "Course translated")

    def test_invalid_response_does_not_publish_output(self):
        class InvalidTranslator:
            def respond_json(self, *args, **kwargs):
                return {"paragraphs": []}
        with tempfile.TemporaryDirectory() as temporary:
            source, output = Path(temporary) / "input.pptx", Path(temporary) / "out.pptx"
            with zipfile.ZipFile(source, "w") as package:
                presentation_parts(package)
                package.writestr("ppt/slides/slide1.xml", '<a:p xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main"><a:r><a:t>Test</a:t></a:r></a:p>')
            with self.assertRaises(ValueError):
                translate_package(source, output, InvalidTranslator(), "German")
            self.assertFalse(output.exists())
