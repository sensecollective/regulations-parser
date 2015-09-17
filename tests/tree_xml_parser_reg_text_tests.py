# vim: set encoding=utf-8
from contextlib import contextmanager
from unittest import TestCase

from lxml import etree
from mock import patch

from regparser.tree.depth import markers as mtypes
from regparser.tree.xml_parser import reg_text
from tests.xml_builder import XMLBuilderMixin
from tests.node_accessor import NodeAccessorMixin


class RegTextTest(XMLBuilderMixin, NodeAccessorMixin, TestCase):
    @contextmanager
    def section(self, part=8675, section=309, subject="Definitions."):
        """Many tests need a SECTION tag followed by the SECTNO and SUBJECT"""
        with self.tree.builder("SECTION") as root:
            root.SECTNO(u"§ {}.{}".format(part, section))
            root.SUBJECT(subject)
            yield root

    def test_build_from_section_intro_text(self):
        with self.section() as root:
            root.P("Some content about this section.")
            root.P("(a) something something")
        node = reg_text.build_from_section('8675', self.tree.render_xml())[0]
        node = self.node_accessor(node, ['8675', '309'])
        self.assertEqual('Some content about this section.', node.text.strip())
        self.assertEqual(['a'], node.child_labels)

        self.assertEqual('(a) something something', node['a'].text.strip())
        self.assertEqual([], node['a'].children)

    def test_build_from_section_collapsed_level(self):
        with self.section() as root:
            root.P(_xml=u"""(a) <E T="03">Transfers </E>—(1)
                           <E T="03">Notice.</E> follow""")
            root.P("(2) More text")
            root.P(_xml="""(b) <E T="03">Contents</E> (1) Here""")
            root.P("(2) More text")
        node = reg_text.build_from_section('8675', self.tree.render_xml())[0]
        node = self.node_accessor(node, ['8675', '309'])
        self.assertEqual(['a', 'b'], node.child_labels)
        self.assertEqual(['1', '2'], node['a'].child_labels)
        self.assertEqual(['1', '2'], node['b'].child_labels)

    def test_build_from_section_collapsed_level_emph(self):
        with self.section() as root:
            root.P("(a) aaaa")
            root.P("(1) 1111")
            root.P("(i) iiii")
            root.P(_xml=u"""(A) AAA—(<E T="03">1</E>) eeee""")
            root.STARS()
        node = reg_text.build_from_section('8675', self.tree.render_xml())[0]
        node = self.node_accessor(node, ['8675', '309'])
        a1iA = node['a']['1']['i']['A']
        self.assertEqual(u"(A) AAA—", a1iA.text)
        self.assertEqual(['1'], a1iA.child_labels)
        self.assertEqual("(1) eeee", a1iA['1'].text.strip())

    def test_build_from_section_double_collapsed(self):
        with self.section() as root:
            root.P(_xml=u"""(a) <E T="03">Keyterm</E>—(1)(i) Content""")
            root.P("(ii) Content2")
        node = reg_text.build_from_section('8675', self.tree.render_xml())[0]
        node = self.node_accessor(node, ['8675', '309'])
        self.assertEqual(['a'], node.child_labels)
        self.assertEqual(['1'], node['a'].child_labels)
        self.assertEqual(['i', 'ii'], node['a']['1'].child_labels)

    def test_build_from_section_reserved(self):
        with self.tree.builder("SECTION") as root:
            root.SECTNO(u"§ 8675.309")
            root.RESERVED("[Reserved]")
        node = reg_text.build_from_section('8675', self.tree.render_xml())[0]
        self.assertEqual(node.label, ['8675', '309'])
        self.assertEqual(u'§ 8675.309 [Reserved]', node.title)
        self.assertEqual([], node.children)

    def test_build_from_section_reserved_range(self):
        with self.tree.builder("SECTION") as root:
            root.SECTNO(u"§§ 8675.309-8675.311")
            root.RESERVED("[Reserved]")
        n309, n310, n311 = reg_text.build_from_section(
            '8675', self.tree.render_xml())
        self.assertEqual(n309.label, ['8675', '309'])
        self.assertEqual(n310.label, ['8675', '310'])
        self.assertEqual(n311.label, ['8675', '311'])
        self.assertEqual(u'§ 8675.309 [Reserved]', n309.title)
        self.assertEqual(u'§ 8675.310 [Reserved]', n310.title)
        self.assertEqual(u'§ 8675.311 [Reserved]', n311.title)

    def _setup_for_ambiguous(self, final_par):
        with self.section() as root:
            root.P("(g) Some Content")
            root.P("(h) H Starts")
            root.P("(1) H-1")
            root.P("(2) H-2")
            root.P("(i) Is this 8675-309-h-2-i or 8675-309-i")
            root.P(final_par)
        node = reg_text.build_from_section('8675', self.tree.render_xml())[0]
        return self.node_accessor(node, ['8675', '309'])

    def test_build_from_section_ambiguous_ii(self):
        n8675_309 = self._setup_for_ambiguous("(ii) A")
        self.assertEqual(['g', 'h'], n8675_309.child_labels)
        self.assertEqual(['1', '2'], n8675_309['h'].child_labels)
        self.assertEqual(['i', 'ii'], n8675_309['h']['2'].child_labels)

    def test_build_from_section_ambiguous_A(self):
        n8675_309 = self._setup_for_ambiguous("(A) B")
        self.assertEqual(['g', 'h'], n8675_309.child_labels)
        self.assertEqual(['1', '2'], n8675_309['h'].child_labels)
        self.assertEqual(['i'], n8675_309['h']['2'].child_labels)
        self.assertEqual(['A'], n8675_309['h']['2']['i'].child_labels)

    def test_build_from_section_ambiguous_1(self):
        n8675_309 = self._setup_for_ambiguous("(1) C")
        self.assertEqual(['g', 'h', 'i'], n8675_309.child_labels)

    def test_build_from_section_ambiguous_3(self):
        n8675_309 = self._setup_for_ambiguous("(3) D")
        self.assertEqual(['g', 'h'], n8675_309.child_labels)
        self.assertEqual(['1', '2', '3'], n8675_309['h'].child_labels)
        self.assertEqual(['i'], n8675_309['h']['2'].child_labels)

    def test_build_from_section_collapsed(self):
        with self.section() as root:
            root.P("(a) aaa")
            root.P("(1) 111")
            root.P(_xml=u"""(2) 222—(i) iii. (A) AAA""")
            root.P("(B) BBB")
        n309 = reg_text.build_from_section('8675', self.tree.render_xml())[0]
        n309 = self.node_accessor(n309, ['8675', '309'])
        self.assertEqual(['a'], n309.child_labels)
        self.assertEqual(['1', '2'], n309['a'].child_labels)
        self.assertEqual(['i'], n309['a']['2'].child_labels)
        self.assertEqual(['A', 'B'], n309['a']['2']['i'].child_labels)

    def test_build_from_section_italic_levels(self):
        with self.section() as root:
            root.P("(a) aaa")
            root.P("(1) 111")
            root.P("(i) iii")
            root.P("(A) AAA")
            root.P(_xml="""(<E T="03">1</E>) i1i1i1""")
            root.P(_xml="""\n(<E T="03">2</E>) i2i2i2""")
        node = reg_text.build_from_section('8675', self.tree.render_xml())[0]
        node = self.node_accessor(node, ['8675', '309'])
        self.assertEqual(['a'], node.child_labels)
        self.assertEqual(['1'], node['a'].child_labels)
        self.assertEqual(['i'], node['a']['1'].child_labels)
        self.assertEqual(['A'], node['a']['1']['i'].child_labels)
        self.assertEqual(['1', '2'], node['a']['1']['i']['A'].child_labels)

    def test_build_from_section_bad_spaces(self):
        with self.section(section=16) as root:
            root.STARS()
            root.P(_xml="""(b)<E T="03">General.</E>Content Content.""")
        node = reg_text.build_from_section('8675', self.tree.render_xml())[0]
        node = self.node_accessor(node, ['8675', '16'])
        self.assertEqual(['b'], node.child_labels)
        self.assertEqual(node['b'].text.strip(),
                         "(b) General. Content Content.")

    def test_build_from_section_section_with_nondigits(self):
        with self.section(section="309a") as root:
            root.P("Intro content here")
        node = reg_text.build_from_section('8675', self.tree.render_xml())[0]
        self.assertEqual(node.label, ['8675', '309a'])
        self.assertEqual(0, len(node.children))

    def test_build_from_section_fp(self):
        with self.section() as root:
            root.P("(a) aaa")
            root.P("(b) bbb")
            root.FP("fpfpfp")
            root.P("(c) ccc")
        node = reg_text.build_from_section('8675', self.tree.render_xml())[0]
        node = self.node_accessor(node, ['8675', '309'])
        self.assertEqual(['a', 'b', 'c'], node.child_labels)
        self.assertEqual([], node['a'].child_labels)
        self.assertEqual(['p1'], node['b'].child_labels)
        self.assertEqual([], node['b']['p1'].child_labels)
        self.assertEqual([], node['c'].child_labels)

    def test_build_from_section_table(self):
        """Account for regtext with a table"""
        with self.section() as root:
            root.P("(a) aaaa")
            with root.GPOTABLE(CDEF="s25,10", COLS=2, OPTS="L2,i1") as table:
                with table.BOXHD() as hd:
                    hd.CHED(H=1)
                    hd.CHED("Header", H=1)
                with table.ROW() as row:
                    row.ENT("Left content", I="01")
                    row.ENT("Right content")
        node = reg_text.build_from_section('8675', self.tree.render_xml())[0]
        node = self.node_accessor(node, ['8675', '309'])
        self.assertEqual(['a'], node.child_labels)
        self.assertEqual(['p1'], node['a'].child_labels)
        self.assertEqual("||Header|\n|---|---|\n|Left content|Right content|",
                         node['a']['p1'].text)
        self.assertEqual("GPOTABLE", node['a']['p1'].source_xml.tag)

    def test_build_form_section_extract(self):
        """Account for paragraphs within an EXTRACT tag"""
        with self.section() as root:
            root.P("(a) aaaa")
            with root.EXTRACT() as extract:
                extract.P("1. Some content")
                extract.P("2. Other content")
        node = reg_text.build_from_section('8675', self.tree.render_xml())[0]

        a = node.children[0]
        self.assertEqual(1, len(a.children))
        extract = a.children[0]
        self.assertEqual(['8675', '309', 'a', 'p1'], extract.label)
        content = ["```extract", "1. Some content", "2. Other content", "```"]
        self.assertEqual("\n".join(content), extract.text)

    def test_build_form_section_notes(self):
        """Account for paragraphs within a NOTES tag"""
        with self.section() as root:
            root.P("(a) aaaa")
            with root.NOTES() as extract:
                extract.P("1. Some content")
                extract.P("2. Other content")
        node = reg_text.build_from_section('8675', self.tree.render_xml())[0]

        a = node.children[0]
        self.assertEqual(1, len(a.children))
        extract = a.children[0]
        self.assertEqual(['8675', '309', 'a', 'p1'], extract.label)
        content = ["```note", "1. Some content", "2. Other content", "```"]
        self.assertEqual("\n".join(content), extract.text)

    def test_get_title(self):
        with self.tree.builder("PART") as root:
            root.HD("regulation title")
        title = reg_text.get_title(self.tree.render_xml())
        self.assertEqual(u'regulation title', title)

    def test_get_reg_part(self):
        """Test various formats for the Regulation part to be present in a
        CFR-XML document"""
        xmls = []
        xmls.append(u"<PART><EAR>Pt. 204</EAR></PART>")
        xmls.append(u"<FDSYS><HEADING>PART 204</HEADING></FDSYS>")
        xmls.append(u"<FDSYS><GRANULENUM>204</GRANULENUM></FDSYS>")
        for xml_str in xmls:
            part = reg_text.get_reg_part(etree.fromstring(xml_str))
            self.assertEqual(part, '204')

    def test_get_reg_part_fr_notice_style(self):
        with self.tree.builder("REGTEXT", PART="204") as root:
            root.SECTION("\n")
        part = reg_text.get_reg_part(self.tree.render_xml())
        self.assertEqual(part, '204')

    def test_get_subpart_title(self):
        with self.tree.builder("SUBPART") as root:
            root.HD(u"Subpart A—First subpart")
        subpart_title = reg_text.get_subpart_title(self.tree.render_xml())
        self.assertEqual(subpart_title, u'Subpart A—First subpart')

    def test_get_subpart_title_reserved(self):
        with self.tree.builder("SUBPART") as root:
            root.RESERVED("Subpart J [Reserved]")
        subpart_title = reg_text.get_subpart_title(self.tree.render_xml())
        self.assertEqual(subpart_title, u'Subpart J [Reserved]')

    def test_build_subpart(self):
        with self.tree.builder("SUBPART") as root:
            root.HD(u"Subpart A—First subpart")
            with root.SECTION() as section:
                section.SECTNO(u"§ 8675.309")
                section.SUBJECT("Definitions.")
                section.P("Some content about this section.")
                section.P("(a) something something")
            with root.SECTION() as section:
                section.SECTNO(u"§ 8675.310")
                section.SUBJECT("Definitions.")
                section.P("Some content about this section.")
                section.P("(a) something something")
        subpart = reg_text.build_subpart('8675', self.tree.render_xml())
        self.assertEqual(subpart.node_type, 'subpart')
        self.assertEqual(len(subpart.children), 2)
        self.assertEqual(subpart.label, ['8675', 'Subpart', 'A'])
        child_labels = [c.label for c in subpart.children]
        self.assertEqual([['8675', '309'], ['8675', '310']], child_labels)

    def test_build_subjgrp(self):
        with self.tree.builder("SUBJGRP") as root:
            root.HD(u"Changes of Ownership")
            with root.SECTION() as section:
                section.SECTNO(u"§ 479.42")
                section.SUBJECT("Changes through death of owner.")
                section.P(u"Whenever any person who has paid […] conditions.")
            with root.SECTION() as section:
                section.SECTNO(u"§ 479.43")
                section.SUBJECT("Changes through bankruptcy of owner.")
                section.P(u"A receiver or referee in bankruptcy may […] paid.")
                section.P("(a) something something")
        subpart = reg_text.build_subjgrp('479', self.tree.render_xml(), [])
        self.assertEqual(subpart.node_type, 'subpart')
        self.assertEqual(len(subpart.children), 2)
        self.assertEqual(subpart.label, ['479', 'Subjgrp', 'CoO'])
        child_labels = [c.label for c in subpart.children]
        self.assertEqual([['479', '42'], ['479', '43']], child_labels)

    def test_get_markers(self):
        text = u'(a) <E T="03">Transfer </E>—(1) <E T="03">Notice.</E> follow'
        markers = reg_text.get_markers(text, mtypes.STARS_TAG)
        self.assertEqual(markers, [u'a', u'1'])

    def test_get_markers_and_text(self):
        text = u'(a) <E T="03">Transfer </E>—(1) <E T="03">Notice.</E> follow'
        wrap = '<P>%s</P>' % text

        doc = etree.fromstring(wrap)
        markers = reg_text.get_markers(text, mtypes.STARS_TAG)
        result = reg_text.get_markers_and_text(doc, markers)

        markers = [r[0] for r in result]
        self.assertEqual(markers, [u'a', u'1'])

        text = [r[1][0] for r in result]
        self.assertEqual(text, [u'(a) Transfer —', u'(1) Notice. follow'])

        tagged = [r[1][1] for r in result]
        self.assertEqual(
            tagged,
            [u'(a) <E T="03">Transfer </E>—',
             u'(1) <E T="03">Notice.</E> follow'])

    def test_get_markers_and_text_emph(self):
        text = '(A) aaaa. (<E T="03">1</E>) 1111'
        xml = etree.fromstring('<P>%s</P>' % text)
        markers = reg_text.get_markers(text, mtypes.STARS_TAG)
        result = reg_text.get_markers_and_text(xml, markers)

        a, a1 = result
        self.assertEqual(('A', ('(A) aaaa. ', '(A) aaaa. ')), a)
        self.assertEqual(('<E T="03">1</E>', ('(1) 1111',
                                              '(<E T="03">1</E>) 1111')), a1)

    def test_get_markers_and_text_deceptive_single(self):
        """Don't treat a single marker differently than multiple, there might
        be prefix text"""
        node = etree.fromstring('<P>Words then (a) a subparagraph</P>')
        results = reg_text.get_markers_and_text(node, ['a'])
        self.assertEqual(len(results), 2)
        prefix, subpar = results

        self.assertEqual(prefix[0], mtypes.MARKERLESS)
        self.assertEqual(prefix[1][0], 'Words then ')
        self.assertEqual(subpar[0], 'a')
        self.assertEqual(subpar[1][0], '(a) a subparagraph')

    def test_get_markers_bad_citation(self):
        text = '(vi)<E T="03">Keyterm.</E>The information required by '
        text += 'paragraphs (a)(2), (a)(4)(iii), (a)(5), (b) through (d), '
        text += '(f), and (g) with respect to something, (i), (j), (l) '
        text += 'through (p), (q)(1), and (r) with respect to something.'
        self.assertEqual(['vi'], reg_text.get_markers(text))

    def test_get_markers_collapsed(self):
        """Only find collapsed markers if they are followed by a marker in
        sequence"""
        text = u'(a) <E T="03">aaa</E>—(1) 111. (i) iii'
        self.assertEqual(reg_text.get_markers(text), ['a'])
        self.assertEqual(reg_text.get_markers(text, 'b'), ['a'])
        self.assertEqual(reg_text.get_markers(text, 'A'), ['a', '1', 'i'])
        self.assertEqual(reg_text.get_markers(text, 'ii'), ['a', '1', 'i'])
        self.assertEqual(reg_text.get_markers(text, mtypes.STARS_TAG),
                         ['a', '1', 'i'])
        self.assertEqual(reg_text.get_markers(text, '2'), ['a', '1'])

    @patch('regparser.tree.xml_parser.reg_text.content')
    def test_preprocess_xml(self, content):
        with self.tree.builder("CFRGRANULE") as root:
            with root.PART() as part:
                with part.APPENDIX() as appendix:
                    appendix.TAG("Other Text")
                    with appendix.GPH(DEEP=453, SPAN=2) as gph:
                        gph.GID("ABCD.0123")
        content.Macros.return_value = [
            ("//GID[./text()='ABCD.0123']/..",
             """<HD SOURCE="HD1">Some Title</HD><GPH DEEP="453" SPAN="2">"""
             """<GID>EFGH.0123</GID></GPH>""")]
        orig_xml = self.tree.render_xml()
        reg_text.preprocess_xml(orig_xml)

        self.setUp()
        with self.tree.builder("CFRGRANULE") as root:
            with root.PART() as part:
                with part.APPENDIX() as appendix:
                    appendix.TAG("Other Text")
                    appendix.HD("Some Title", SOURCE="HD1")
                    with appendix.GPH(DEEP=453, SPAN=2) as gph:
                        gph.GID("EFGH.0123")

        self.assertEqual(etree.tostring(orig_xml), self.tree.render_string())

    def test_build_from_section_double_alpha(self):
        # Ensure we match a hierarchy like (x), (y), (z), (aa), (bb)…
        with self.tree.builder("SECTION") as root:
            root.SECTNO(u"§ 8675.309")
            root.SUBJECT("Definitions.")
            root.P("(aa) This is what things mean:")
        node = reg_text.build_from_section('8675', self.tree.render_xml())[0]
        child = node.children[0]
        self.assertEqual('(aa) This is what things mean:', child.text.strip())
        self.assertEqual(['8675', '309', 'aa'], child.label)

    def test_build_tree_with_subjgrp(self):
        """XML with SUBJGRPs where SUBPARTs are shouldn't cause a problem"""
        with self.tree.builder("ROOT") as root:
            with root.PART() as part:
                part.EAR("Pt. 123")
                part.HD(u"PART 123—SOME STUFF", SOURCE="HED")
                with part.SUBPART() as subpart:
                    subpart.HD(u"Subpart A—First subpart")
                with part.SUBJGRP() as subjgrp:
                    subjgrp.HD(u"Changes of Ownership")
                with part.SUBPART() as subpart:
                    subpart.HD(u"Subpart B—First subpart")
                with part.SUBJGRP() as subjgrp:
                    subjgrp.HD(u"Another Top Level")
        node = reg_text.build_tree(self.tree.render_xml())
        self.assertEqual(node.label, ['123'])
        self.assertEqual(4, len(node.children))
        subpart_a, subjgrp_1, subpart_b, subjgrp_2 = node.children
        self.assertEqual(subpart_a.label, ['123', 'Subpart', 'A'])
        self.assertEqual(subpart_b.label, ['123', 'Subpart', 'B'])
        self.assertEqual(subjgrp_1.label, ['123', 'Subjgrp', 'CoO'])
        self.assertEqual(subjgrp_2.label, ['123', 'Subjgrp', 'ATL'])


class MarkerMatcherTests(XMLBuilderMixin, TestCase):
    def test_next_marker_found(self):
        """Find the first paragraph marker following a paragraph"""
        with self.tree.builder("ROOT") as root:
            root.P("(A) AAA")
            root.P("ABCD")
            root.P("(d) ddd")
            root.P("(1) 111")
        xml = self.tree.render_xml()[1]
        self.assertEqual(reg_text.MarkerMatcher().next_marker(xml), 'd')

    def test_next_marker_stars(self):
        """STARS tag has special significance."""
        with self.tree.builder("ROOT") as root:
            root.P("(A) AAA")
            root.P("ABCD")
            root.STARS()
            root.P("(d) ddd")
            root.P("(1) 111")
        xml = self.tree.render_xml()[1]
        self.assertEqual(reg_text.MarkerMatcher().next_marker(xml),
                         mtypes.STARS_TAG)

    def test_next_marker_none(self):
        """If no marker is present, return None"""
        with self.tree.builder("ROOT") as root:
            root.P("(1) 111")
            root.P("Content")
        xml = self.tree.render_xml()[0]
        self.assertIsNone(reg_text.MarkerMatcher().next_marker(xml))
