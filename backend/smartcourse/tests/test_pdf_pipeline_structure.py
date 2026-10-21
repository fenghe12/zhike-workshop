import unittest
from unittest.mock import patch
from app.pdf_input import pdf_pipeline_structure
from app.pdf_input import _span_text


class PdfPipelineStructureTests(unittest.TestCase):
    def test_character_coordinates_restore_word_spaces(self):
        span={'size':20,'chars':[{'c':'뉴','bbox':[0,0,10,20]},{'c':'런','bbox':[10,0,20,20]},
              {'c':'모','bbox':[25,0,35,20]},{'c':'델','bbox':[35,0,45,20]}]}
        self.assertEqual(_span_text(span),'뉴런 모델')
    def test_page_order_original_geometry_and_exact_script_are_preserved(self):
        originals=[]
        for page_id in (1,2):
            originals.append({'page_id':page_id,'title':f'Title {page_id}',
                'script_text':f'讲稿 {page_id}\n保留原段落。','width':720,'height':405,
                'rotation':0,'imageRegions':[{'bbox':[20,30,200,150]}],
                'textBlocks':[{'lines':[{'spans':[{'text':f'Body {page_id}'}]}]}]})
        with patch('app.pdf_input.bind_pdf_lecture',return_value={'source':'/course.pdf','pages':originals}):
            result=pdf_pipeline_structure('/course.pdf','/script.docx','task-one')
        self.assertEqual(result['input_mode'],'existing_pdf')
        self.assertEqual(result['total_pages'],2)
        self.assertEqual([p['page_id'] for p in result['pages']],[1,2])
        for page,original in zip(result['pages'],originals):
            self.assertEqual(page['script_text'],original['script_text'])
            self.assertEqual(page['layout']['pdf_page'],original)
            self.assertEqual(page['layout']['slide_width'],960)
            self.assertEqual(page['key_points'],[f"Body {page['page_id']}"])
