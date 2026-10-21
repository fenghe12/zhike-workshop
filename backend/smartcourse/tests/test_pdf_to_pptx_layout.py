import unittest

import pymupdf

from app.pdf_to_pptx import _visual_text_lines


class PdfToPptxLayoutTests(unittest.TestCase):
    def test_visual_order_and_columns(self):
        document=pymupdf.open()
        page=document.new_page(width=450,height=180)
        page.insert_text((110,70),'world',fontsize=20)
        page.insert_text((300,70),'Right',fontsize=20)
        page.insert_text((40,70),'Hello ',fontsize=20)
        page.insert_text((40,125),'z = 2x + 1',fontsize=20)
        rows=_visual_text_lines(page)
        self.assertEqual([row['text'] for row in rows],['Hello world','Right','z = 2x + 1'])
        self.assertEqual([row['preserveAsImage'] for row in rows],[False,False,True])
        document.close()


if __name__=='__main__':
    unittest.main()
