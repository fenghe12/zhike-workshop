import unittest
from lxml import etree as E
from app.pptx_math_images import A, P, R, MC, NS, make_fallback_picture


class FallbackPictureTests(unittest.TestCase):
    def fixture(self):
        return E.fromstring(f'''<mc:Fallback xmlns:mc="{MC}" xmlns:p="{P}" xmlns:a="{A}" xmlns:r="{R}">
          <p:sp><p:nvSpPr><p:cNvPr id="3" name="Formula"/></p:nvSpPr>
          <p:spPr><a:blipFill><a:blip r:embed="rId7"/></a:blipFill></p:spPr>
          <p:txBody><a:p><a:r><a:t> </a:t></a:r></a:p></p:txBody></p:sp>
        </mc:Fallback>''')

    def test_inherited_coordinates_become_explicit_picture_size(self):
        fallback = self.fixture()
        transform = E.fromstring(f'<a:xfrm xmlns:a="{A}"><a:off x="15" y="20"/><a:ext cx="800" cy="450"/></a:xfrm>')
        make_fallback_picture(fallback, fallback.find('.//a:blip', NS), transform)
        self.assertIsNone(fallback.find('p:sp', NS))
        picture = fallback.find('p:pic', NS)
        self.assertEqual(picture.find('p:spPr/a:xfrm/a:ext', NS).attrib, {'cx': '800', 'cy': '450'})
        self.assertEqual(picture.find('p:blipFill/a:blip', NS).get('{'+R+'}embed'), 'rId7')
        self.assertIsNotNone(picture.find('p:blipFill/a:stretch/a:fillRect', NS))
        self.assertEqual(picture.find('p:nvPicPr/p:cNvPr', NS).get('id'), '3')

    def test_does_not_discard_additional_fallback_text(self):
        fallback = self.fixture()
        fallback.find('.//a:t', NS).text = 'Additional information'
        transform = E.fromstring(f'<a:xfrm xmlns:a="{A}"/>')
        with self.assertRaisesRegex(ValueError, 'additional text'):
            make_fallback_picture(fallback, fallback.find('.//a:blip', NS), transform)


if __name__ == '__main__':
    unittest.main()
