"""Current brand assets are derived, accessible and separate from frozen evidence."""
from pathlib import Path
import unittest
import xml.etree.ElementTree as ET
from tools.build_brand_assets import build

ROOT = Path(__file__).resolve().parents[1]


class BrandAssetTests(unittest.TestCase):
    def test_assets_match_generator_and_have_no_executable_or_remote_dependencies(self):
        for name, text in build().items():
            self.assertEqual((ROOT / name).read_text(encoding='utf-8'), text)
            tree = ET.fromstring(text)
            self.assertEqual(tree.attrib['role'], 'img')
            for el in tree.iter():
                self.assertNotIn(el.tag.split('}')[-1], ('script', 'foreignObject', 'image'))
                self.assertFalse(any(k.lower().startswith('on') for k in el.attrib))

    def test_default_picture_is_static_with_explicit_motion_opt_in(self):
        for name in ('README.md', 'README.zh-CN.md'):
            text = (ROOT / name).read_text(encoding='utf-8')
            self.assertIn('prefers-reduced-motion: no-preference', text)
            self.assertIn('src="assets/brand/hero-light-static.svg"', text)
            self.assertIn('name', (ROOT / 'chat_distiller/skills/carrytrace/SKILL.md').read_text())

    def test_current_homepages_have_new_links_and_compatibility_boundary(self):
        for name in ('README.md', 'README.zh-CN.md'):
            text = (ROOT / name).read_text(encoding='utf-8')
            self.assertIn('# CarryTrace', text)
            self.assertNotIn('https://github.com/Anhao1314/chat-distiller', text)
            self.assertIn('~/.chat-distiller', text)
            self.assertIn('chat_distiller', text)


if __name__ == '__main__':
    unittest.main()
