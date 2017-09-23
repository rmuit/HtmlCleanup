"""Helper class containing methods that can be used by a HTML cleanup script.

The SoupCleanupHelper class works with Beautifulsoup v3.

The best way to start using this is first read a script which uses these
classes. There is a preferred order of calling methods; some methods assume that
other cleanup operations have been done already on the HTML.

Some methods throw exceptions for un-parseable HTML; they are not documented
properly yet.
"""

"""
About whitespace-ish stuff in an HTML document: there are different kinds:
- <br>s. These are generally kept because they influence the output, but:
  - A single <br> at the end of a block-level tag makes no difference and we
    would like to remove those if possible (because a bit ugly/confusing).
    strip_non_inline_whitespace() does this.
  - Two consecutive <br>s in a paragraph can be converted into two separate
    paragraphs. split_paragraphs_containing_double_br() does this.
- Regular spaces. (Possible) policy for scripts:
  - Remove them at the end of block-level tags / <p>; they don't do anything.
  - Also from the beginning. (A single start of a <p> does not show up in a
    rendered document.)
  - Further remove duplicate spaces (within most tags? not <pre>). Actually
    this is not just 'within tags' but also if there is one space just outside
    an 'inline' tag and one just inside, these should ideally be deduplicated.
    - A way to do this is to move spaces at the start/end of an inline tag's
      contents to just outside, and then de-duplicate. As done by
      move_whitespace_to_parent() and dedupe_whitespace().
- Non-breaking spaces. Policy: dedupe _single_ non-breaking spaces which are
  adjacent to regular spacing, just like the regular spacing (i.e. replace all
  by a single space or newline) - if they are not at the start of a rendered
  line. (See starts_rendered_line().)
  - This removal actually changes the rendered document: it influences the
    horizontal spacing between the adjacent elements. So maybe we don't always
    want to do that / this is be reflected in a class variable. But example
    MSFP documents show that apparently non-breaking spaces are often inserted
    accidentally, and therefore are better removed.
  - We do not want to dedupe multiple &nbsp;s; we assume those are always
    inserted on purpose.
  - We do not want to replace standalone &nbsp;s; (surrounded by non-spaces or
    inline tags on both sides) by normal spaces; that influences the breaking
    of lines and we won't mess with that / will assume those are always
    inserted on purpose.
  We also do not want to remove them from the start of non-inline tags because
  they make a difference there (which we assume to be intended because that's
  visible to a Frontpage document editor); we do remove them from the end of
  non-inline tags and just before <br>s (just like other spaces).See
  'generally' below for inline tags.
- Newlines. These have the same function as a single space in the output; they
  are only there for formatting the HTML. Our policy:
  - Make no assumptions about whether the HTML has any formatting.
  - Keep newlines after the end of block-level elements, <p> and <br>.
  - Remove newlines from inline elements and within <p> which are not preceded
    by <br>. (This is slightly contentious as it could remove some nice
    formatting, however since we are shortening a lot of lines by removing
    unnecessary style tags from a.o.<p>, it also looks strange if we keep the
    newlines there.)
Generally, recommended for any of the 4 kinds of whitespace:
- Do not leave leading/trailing whitespace inside inline tags but move them
  just outside (for unification of the document, and enabling other cleanup
  code to do its work more easily; it does not make visible difference).
- Strip trailing whitespace (except newlines) at the end of non-inline tags
  and just before <br>. They don't make a visible difference but are
  unnecessary cruft.
"""

import re
from BeautifulSoup import Tag, NavigableString


class SoupCleanupHelper(object):
    """Utility methods for HTML Cleanup using BeautifulSoup."""

    # Regular expressions we use more often are defined as class members, so we
    # don't need to recompile them every time. I hope that makes sense.
    #
    rx_find_tag = re.compile(r'^\<([^\ >]+)')
    #
    # Regexes containing HTML tags. These can be used for matching:
    # - an element that you don't know is a tag or NavigableString;
    # - the full text representation of a tag.
    # Should not be used on things we know are NavigableStrings, because
    # useless, therefore introducing ambiguity in the code.
    rx_spacehtml_only = re.compile(r'^(?:\s|\&nbsp\;|\<br ?\/?\>)+$')
    #
    # Regexes usable on NavigableStrings.
    # We want to use thse for replacement (specifically by ''). Space excluding
    # "&nbsp;" at the start/end of the contents of a tag don't usually influence
    # formatting of the output, except if they are compound breaking + non-
    # breaking spaces. But even if they influence only formatting of the source
    # HTML, we explicitly want to 'fix' that for spaces at start/end of tag
    # contents.
    #
    # To remember: NavigableStrings include newlines, and \s matches newlines.
    #
    # We use the fillowing for stripping whitespace (re.sub()) in some places
    # but that does not need brackets.
    rx_newline = re.compile(r'\s*\n+\s*')
    rx_nbspace_only = re.compile(r'^(?:\s|\&nbsp\;)+$')
    # We use the following for matching (and then modifying) the whitespace part
    # in a way that needs to access the matches in some places, so use brackets.
    rx_nbspace_at_start = re.compile(r'^((?:\s|\&nbsp\;)+)')
    rx_nbspace_at_end = re.compile(r'((?:\s|\&nbsp\;)+)$')
    rx_spaces_at_start = re.compile(r'^(\s+)')
    rx_multispace = re.compile(r'(\s{2,})')
    rx_multispace_at_start = re.compile(r'^(\s{2,})')
    # Matches only a single consecutive &nbsp. (For this, the negative
    # lookbehind assertion needs to contain only one character because anything
    # else ending in ';' is not whitespace either.)
    rx_multinbspace = re.compile(r'((?:\s|(?<!\;)\&nbsp\;(?!\&nbsp\;)){2,})')
    rx_multinbspace_at_start = re.compile(
        r'^((?:\s|(?<!\;)\&nbsp\;(?!\&nbsp\;)){2,})')
    # The first negative lookbehind assertion for "not at the start of the
    # string", (which amounts to explicitly matching a non-space character
    # which is not the ; in &nbsp;,) is unfortunate. Because now, for doing
    # re.sub(), we need to explicitly put \1 back into the replacement string.
    rx_multinbspace_not_at_start = re.compile(
        r'(\S)(?<!\&nbsp\;)((?:\s|(?<!\;)\&nbsp\;(?!\&nbsp\;)){2,})')

    def __init__(self, soup):
        # Class variables / settings:

        # BeautifulSoup instance.
        self.soup = soup

        # Names of 'inline' tags; used to determine if
        # - We can move spacing to just outside of the tag, without changing
        #   the rendered output; (We assume we can, for inline tags);
        # - A string/tag is at the beginning of a rendered line. (We assume it
        #   is, if it is right after a non-inline tag.)
        # If you have e.g. 'a' tags in your document which are positioned at
        # block level rather than inline... you might need to change this?
        self.inline_tag_names = ['strong', 'em', 'font', 'span', 'a']

        # Dedupe a _single_ &nbsp; that is adjacent to other whitespace, by
        # removing it? (See comments above.)
        self.dedupe_nbsp = True

        # Remove atrributes mentioned in this two-dimensional dict. First key
        # is tagname or '*' to remove the specified attributes for all tags;
        # second key is attribute name (no '*' implemented). Values can be a
        # single attribute value or a list of values for which the attribute
        # should be removed. The single value '*' will always remove the
        # attribute.
        # There are also attributes which are 'hardcoded' and will always be
        # removed/changed; see the code.
        self.remove_attributes = {
            # Remove any language value from any tag.
            '*': {
                'lang': '*',
            },
            # We've seen a website where 'margin-top' is present in almost any
            # paragraph and we don't want this in the output.
            # 'p': { 'margin-top': '*' }
        }
        # Same for the 'style' attribute. (Mentioning 'style' in
        # remove_attributes is possible but discouraged; define styles to
        # remove here, in the same way.)
        self.remove_styles = {
            '*': {
                'line-height': ['100%', 'normal', '15.1 pt'],
                # Remove black everywhere. (May not be what we always want...)
                'color': ['black', '#000', '#000000'],
                'text-autospace': 'none',
            },
            'h2': {'color' : '#996600'},
            'h3': {'color' : '#999900'},
        }

    @staticmethod
    def regex_search(element, regex):
        """Check if element matches regex.

        This is a 'safe' replacement for rx.search(str(e)) where no error will
        be thrown regardless whether element is a tag or NavigableString.
        """
        # Difficulty here: str(ee) may give UnicodeEncodeError with some
        # characters and so may ee.__str__() and repr(ee) (the latter with some
        #  \x?? chars). The only thing sure to not give errors is ee.__repr__().
        # However you don't want to use THAT for matching! So use it as a safety
        # net to make sure str() is not called when unicode chars are in there.
        # (Yeah, I know, it's probably just my limited Python knowledge, that
        # made me write this function...
        # If it isn't a bug in BeautifulSoup 3.1; probably not.)
        s = element.__repr__()
        if s.find('\\u') != -1 or s.find('\\x') != -1:
            return None
        return regex.search(str(element))

    @staticmethod
    def get_index_in_parent(element):
        """Return the index of an element inside parent contents.

        (Maybe there is a better way than this; I used to have this in a patched
        version of the BeautifulSoup.py library 3.1.0.1 itself, before I started
        working with the non-buggy v3.0.8.1. So I just took the function out and
        didn't look further.)
        """
        index = 0
        while index < len(element.parent.contents):
            if element.parent.contents[index] is element:
                return index
            index = index + 1
        # If this happens, something is really wrong with the data structure:
        raise Exception('Internal fatal error: Could not find element back '
                        'inside its own parent!?:' + str(element))

    def get_tag_name(self, element):
        """Return the tag name of an element (or '' if this is not a tag).

        I was surprised I can't find a function like this in BeautifulSoup...
        """
        if element.__class__.__name__ != 'Tag':
            return ''
        m = self.regex_search(element.__repr__(), self.rx_find_tag)
        if m:
            return m.group(1)
        return ''

    @staticmethod
    def get_style_properties(tag):
        """Get style attribute from tag, return it as dictionary of properties.

        Keys always lowercase.
        """
        style_attr = tag.get('style')
        properties = {}
        if style_attr:
            for property_def in style_attr.split(';'):
                if property_def.strip() != '':
                    (name, value) = property_def.split(':', 1)
                    properties[name.strip().lower()] = value.strip()
        return properties

    @staticmethod
    def set_style_property(tag, set_name, set_value):
        """Set style attribute (property=value) in a tag.

        set_name will be lowercased;
        set_value must be string type. If set_value == '' the property is
        deleted.
        """
        style_attr = tag.get('style')
        properties = {}
        set_name = set_name.strip().lower()

        # Deconstruct style.
        if style_attr:
            for property_def in style_attr.split(';'):
                (name, value) = property_def.split(':', 1)
                properties[name.strip().lower()] = value.strip()

            # (Re)build style_attr from here.
            if set_name in properties:
                # Property was present already. Re-compose the full style
                # attribute.
                if set_value != '':
                    properties[set_name] = set_value
                else:
                    del properties[set_name]
                style_attr = ''
                for name in properties:
                    if style_attr != '':
                        style_attr += '; '
                    style_attr += name + ': ' + properties[name]
            elif set_value != '':
                # Add the property to the existing style attribute.
                style_attr = style_attr.strip()
                if style_attr != '':
                    if not style_attr.endswith(';'):
                        style_attr += ';'
                    style_attr += ' '
                style_attr += set_name + ': ' + set_value
        else:
            style_attr = set_name + ': ' + set_value

        # Set style (newly, or overwrite the existing one).
        if style_attr != '':
            tag['style'] = style_attr
        #elif 'style' in tag.attrs: <-- wrong. attrs returns tuples, not keys.
	#so just always 'del' it, regardless of existende.
        else:
            # There's no style left. (There may or may not have been a set_name;
            # if there was, we just deleted it.)
            del tag['style']

    def get_alignment(self, tag):
        """Get alignment from a tag.

        Look in attributes 'align' & 'style: text-align' (in that order). Return
        'left', 'center', 'right' or ''.
        """
        alignment = tag.get('align')
        if not alignment:
            styles = self.get_style_properties(tag)
            if 'text-align' in styles:
                alignment = styles['text-align']
        # align=middle is seen in some images.
        if alignment == 'middle':
            alignment = 'center'
        return alignment

    def set_alignment(self, tag, value):
        """Set alignment (or delete it, by setting value to '').

        Do this in 'text-align' style attribute. (We could also e.g. set a
        certain class, if we wanted...) Delete the 'align' attribute.
        Exception: <img>
        """
        # special handling for images, since the (deprecated?)
        # 'align' tag governs their own alignment - not their contents'
        # alignment. So don't do 'text-align' there.
        if self.get_tag_name(tag) != 'img':
            self.set_style_property(tag, 'text-align', value)
        elif value != '':
            tag['align'] = value
            return
        # text-align is set. Delete the deprecated align attribute (if present).
        del tag['align']
    #== Note: below was the code I was using somewhere else before,
    #   in stead of self.set_style_property(). Maybe we want to go back to using
    #    that someday though I don't think so...
          # Replace this outdated attribute by a 'class="align-..."' attribute
          #  Assumes you have those classes defined in CSS somewhere!
          # (We can also go for a 'style: text-align=...' attribute, but I'd
          # like to have less explicit style attributes in the HTML source if
          # I can, so make a 'layer')
          #sv = t.get('class')
          #if sv:
          #  # assume this class is not yet present
          #  t['class'] = sv + ' align-' + av

          #else:
          #  t['class'] = 'align-' + av
          #av = ''
    #===

    def check_alignment(self, parent_tag, parent_align, allow_parent_change=''):
        """Check / change alignments of elements inside a certain parent tag.

        If alignment of an element is explicitly specified AND equal to the
        specified parent alignment, then delete that explicit attribute.

        allow_parent_change: if alignment of all child elements is the same and
        not equal to the specified parent alignment, then change the parent's
        alignment property (because it has no effect). This is a string which
        can specify an alignment, or 'any'. Empty string means disallow.

        Return value: a dictionary with all child tag alignments seen, as keys.
        A key "CHANGE" (which can only be set if allow_parent_change is
        non-empty) means the alignment of the parent tag should be changed to
        this value; the method does not always do this by itself.
        """
        ## First: special handling for 'implicitly aligning tags', i.e. <center>
        if parent_align == 'center':
            # Get rid of all 'center' tags, because they do nothing. (We're
            # generally better off placing its child contents at the same level
            # now, so we can inspect them in one go.)
            for tag in parent_tag.findAll('center', recursive=False):
                self.move_contents_before(tag, tag)
                tag.extract()

        seen_alignments = {}
        # Non-whitespace NavigableStrings always have alignment equal to the
        # parent element. (Whitespace strings don't matter; alignment can be
        # changed without visible difference.)
        r = self.get_contents(parent_tag, 'nonwhitespace_string')
        if r:
            # Setting 'inherit' effectively means: prevent parent's alignment
            # from being changed.
            seen_alignments['inherit'] = True

        ## Find/index alignment of all tags within parent_tag, and process them.
        for tag in parent_tag.findAll(recursive=False):

            tag_name = self.get_tag_name(tag)
            tag_alignment = self.get_alignment(tag)
            if tag_alignment:
                current_alignment = tag_alignment
                allow_change = 'any'
            elif tag_name == 'center':
                current_alignment = 'center'
                allow_change = parent_align
            else:
                current_alignment = parent_align
                if tag_name == 'p':
                    allow_change = 'any'
                else:
                    allow_change = ''

            # Recurse through sub elements first.
            child_alignments = self.check_alignment(tag, current_alignment, allow_change)
            # Handling of 'implicitly aligning tags', i.e. <center>:
            if tag_name == 'center':
                if 'CHANGE' in child_alignments:
                    # tag_alignment needs change -- which can (only) be done by
                    # deleting the tag.
                    self.move_contents_before(tag, tag)
                    tag.extract()

            else:
                # 'Normal' element.
                if 'CHANGE' in child_alignments:
                    # tag_alignment needs change. (We may end up deleting it
                    # just afterwards, but this way keeps code clean.)
                    self.set_alignment(tag, child_alignments['CHANGE'])
                    tag_alignment = child_alignments['CHANGE']

                if tag_alignment:
                    ## Explicit/changed alignment.
                    if tag_alignment == parent_align:
                        # Delete (now-)superfluous explicit 'align' attribute.
                        self.set_alignment(tag, '')
                        seen_alignments['inherit'] = True
                    else:
                        # We're just collecting alignments 'not equal to
                        # inherited' here; check after the loop what we want to
                        # do about it.
                        last_seen = tag_alignment
                        seen_alignments[last_seen] = True
                else:
                    ## Inherited, unchanged alignment.
                    seen_alignments['inherit'] = True

        ## After finding/indexing(/changing?) all alignments from (recursive?)
        ## child tags:
        #
        # We can change this collection of elements' (and thus the parent's)
        # alignment IF the parent's "align" property has no influence on any of
        # its children - i.e. no "inherit" was recorded.
        if (len(seen_alignments) == 1 and
            'inherit' not in seen_alignments and
            (allow_parent_change == 'any' or allow_parent_change == last_seen)):
            # All alignments are the same == lastalign.
            # Indicate to caller that it should change parent's align attribute.
            seen_alignments['CHANGE'] = last_seen
            # Delete any explicit attribute because we will change the parent's.
            for tag in parent_tag.findAll(align=last_seen, recursive=False):
                self.set_alignment(tag, '')

        return seen_alignments
    # Ideas for this method:
    # - if all your stuff is 'center', and more than one (and not inherit), then
    #   insert a 'center', place everything inside, and then delete all the
    #   explicit align=center from these tags
    # - replace 'middle' by 'center'? (align=middle is used for pictures, I've
    #   seen sometimes.)

    def mangle_attributes(self, tag):
        """Filter out attributes from a tag; change some others.

        This is/must remain idempotent; mangle_tag() may call it several times.
        """
        tag_name = self.get_tag_name(tag)
        # tag.attrs is list of tuples, so if you loop through it, you get tuples
        # back. Still you can _use_ it as a dict type. So you can assign and
        # delete stuff by key, however you may not delete attributes from the
        # tag by key while iterating over its .attrs list! That makes the
        # iterator break off. So create a list of keys first.
        attr_names = []
        for attr in tag.attrs:
            attr_names.append(attr[0])
        for orig_name in attr_names:
            orig_value = tag.get(orig_name)
            name = orig_name.lower()
            value = orig_value.lower()

            # Check if we should remove this attribute.
            remove = False
            if (tag_name in self.remove_attributes and
                    name in self.remove_attributes[tag_name]):
                if isinstance(self.remove_attributes[tag_name][name], list):
                    remove = value in self.remove_attributes[tag_name][name]
                else:
                    remove = self.remove_attributes[tag_name][name] in [value, '*']
            elif ('*' in self.remove_attributes and
                  name in self.remove_attributes['*']):
                if isinstance(self.remove_attributes['*'][name], list):
                    remove = value in self.remove_attributes['*'][name]
                else:
                    remove = self.remove_attributes['*'][name] in [value, '*']
            if remove:
                value = ''

            elif name == 'align':
                # Replace deprecated align attribute by newer way. Unlike the
                # below, this call already resets the 'align' attribute itself,
                # so we do not reset 'value', in order to skip the below code
                # which changes attributes.
                self.set_alignment(tag, value)

            elif name == 'class':
                classes = orig_value.split()
                for value in classes:
                    if value.lower() == 'msonormal':
                        classes.remove(value)
                value = ' '.join(classes)

            elif name == 'style':
                # Loop over style name/values; rebuild the attribute value from
                # scratch.
                value = ''
                for property_def in orig_value.split(';'):
                    if property_def.strip() != '':
                        (p_name, p_value) = property_def.split(':', 1)
                        p_name = p_name.strip()
                        p_value = p_value.strip()
                        # We want to keep case of style name/values but not for
                        # comparison.
                        l_p_name = p_name.lower()
                        l_p_value = p_value.lower()

                        # Check if we should remove this style.
                        remove = False
                        if (tag_name in self.remove_styles and
                                l_p_name in self.remove_styles[tag_name]):
                            if isinstance(
                                    self.remove_styles[tag_name][l_p_name],
                                    list):
                                remove = l_p_value in \
                                         self.remove_styles[tag_name][l_p_name]
                            else:
                                remove = self.remove_styles[tag_name][l_p_name]\
                                         in [l_p_value, '*']
                        elif ('*' in self.remove_styles and
                              l_p_name in self.remove_styles['*']):
                            if isinstance(
                                    self.remove_styles['*'][l_p_name], list):
                                remove = l_p_value in \
                                         self.remove_styles['*'][l_p_name]
                            else:
                                remove = self.remove_styles['*'][l_p_name] in \
                                         [l_p_value, '*']
                        if remove:
                            p_value = ''

                        elif p_name.startswith('margin'):
                            # Always remove small margins.
                            if (p_value.isnumeric() and
                                    float(p_value) < 0.02):
                                p_value = ''

                        elif p_name.startswith('mso-'):
                            # Weird office specific styles? Never check, just
                            # delete and hope they didn't do anything.
                            p_value = ''

                        # Re-add the style value, unless we discarded it.
                        if p_value:
                            if value != '':
                                value += '; '
                            value += p_name + ': ' + p_value

            # Check if attributes have changed (but don't change case only);
            # always change attribute names to lower case.
            if name != orig_name or value != orig_value.lower():
                if name != orig_name or not value:
                    del tag[orig_name]
                if value:
                    tag[name] = value

    def mangle_tag(self, tag):
        """Try to move all attributes out of the current tag.

        We try to move attributes into parent or only child; if this is possible
        or the tag has no attributes, remove the tag (after moving the tag
        contents outside of it).

        This can also change/delete attributes.

        This can be used to remove inline tags which have no semantic meaning.
        (So e.g. not <p> because that's not inline and changes positioning; not
        <em> because that has semantic meaning and changes how its contents are
        printed. But span and 'non-link anchors'.) There's special handling for:
        - <font> which we always want to remove: if we cannot move all its
          attributes somewhere else then we replace it by a <span>.
        - <a> which only hold a name; we replace it by an id in another tag if
          that doesn't have one yet.
        """
        dest = None
        dest_is_child = False
        dest_is_new = False

        tag_name = self.get_tag_name(tag)
        # Do pre-check for <a> to prevent needless processing: we only process
        # non-'href' tags with a name attribute and no id. (Tags without href
        # _or_ name are strange enough to leave alone.)
        if (tag_name == 'a' and
                (not tag.get('name') or tag.get('id') or tag.get('href'))):
            return

        # Decide which is going to be the 'destination' tag, where we will move
        # any style attributes to:
        #
        # Check for single child element which can hold style attributes. (It
        # seems like this is preferred over a parent element, because we prefer
        # putting styles in the most specific one.) Note we will also match
        # 'position' tags even though they should never be found inside 'inline'
        # tags; if this ever happens, then we will surely want to get rid of
        # the 'inline' tag.
        #
        # Find child non-space NavigableStrings(?): should find nothing.
        r1 = self.get_contents(tag, 'nonwhitespace_string')
        if not r1:
            # Find child tags: should find one tag.
            r1 = self.get_contents(tag, 'tags')
            if len(r1) == 1:
                name = self.get_tag_name(r1[0])
                if name in ['a', 'p', 'span', 'div', 'h2', 'h3', 'h4', 'li', 'blockquote']:
                    # A last deal breaker is if both tag and the destination
                    # have an id.
                    if not ((tag_name == 'a' or tag.get('id')) and
                            r1[0].get('id')):
                        dest = r1[0]
                        dest_is_child = True
        if dest is None:
            # Check for parent element which can hold style attributes, and
            # where the tag is the only child - except for 'a' which is allowed
            # to have siblings.
            parent_tag = tag.parent
            name = self.get_tag_name(parent_tag)
            # (XHTML specified that blockquote must contain block-level
            # elements. No more; in HTML it may contain just text.)
            if name in ['a', 'p', 'span', 'div', 'h2', 'h3', 'h4', 'li', 'blockquote']:
                r1 = self.get_contents(parent_tag, 'tags')
                if len(r1) == 1:
                    r1 = []
                    if tag_name != 'a':
                        r1 = self.get_contents(parent_tag, 'nonwhitespace_string')
                    if not r1:
                        if not ((tag_name == 'a' or tag.get('id')) and
                                parent_tag.get('id')):
                            dest = parent_tag

        if dest is None:
            if tag_name == 'font':
                # Cannot use a direct parent/child. Make new <span> to replace
                # the <font>. This could be weird in theory; there could be a
                # font tag surrounding one or several block-level elements;
                # putting a span there is frowned upon, if not illegal. However,
                # leaving a 'font' tag is probably equally bad... For the
                # moment, we are just hoping that we have cleaned up all font
                # tags where this is the case, above.
                dest = Tag(self.soup, 'span')
                parent_tag.insert(self.get_index_in_parent(tag), dest)
                dest_is_new = True
            else:
                # We cannot merge this tag into another one, but we'll also
                # change attributes here if necessary.
                self.mangle_attributes(tag)
                # If the tag itself has no implicit meaning, remove it. (The
                # <div> is disputable; it's not 100% sure that removing an empty
                # one will not influence positioning/grouping. But we assume for
                # MS Frontpage pages they are superfluous. See also: comments at
                # caller.)
                if not tag.attrs and tag_name in ['span', 'div']:
                    self.move_contents_before(tag, tag)
                    tag.extract()
                return

        # Before we merge attributes, normalize their names/values.
        self.mangle_attributes(dest)
        merge_classes = ''
        merge_styles = {}
        # Get the attributes (excl. style) and styles to merge into destination.
        if tag_name == 'font':
            # Iterate over attributes and convert them all into styles; don't
            # move any attributes as-is. (Note: you get attributes as a list of
            # tuples.) We may not delete attributes from the tag by key while
            # iterating over its .attrs list; that makes the iterator break.
            # Create a list of keys first.
            attr_names = []
            for attr in tag.attrs:
                attr_names.append(attr[0])
            for orig_name in attr_names:
                name = orig_name.lower()
                value = tag.get(orig_name)
                style_name = ''

                # Check if we should remove this attribute.
                remove = False
                if ('font' in self.remove_attributes and
                        name in self.remove_attributes['font']):
                    if isinstance(self.remove_attributes['font'][name], list):
                        remove = value in self.remove_attributes['font'][name]
                    else:
                        remove = self.remove_attributes['font'][name] in [
                            value, '*']
                elif ('*' in self.remove_attributes and
                      name in self.remove_attributes['*']):
                    if isinstance(self.remove_attributes['*'][name], list):
                        remove = value in self.remove_attributes['*'][name]
                    else:
                        remove = self.remove_attributes['*'][name] in [
                            value, '*']
                if remove:
                    # Fall through but also remove the tag, for the len() check.
                    del tag[name]

                elif name == 'color':
                    style_name = 'color'
                elif name == 'face':
                    style_name = 'font-family'
                elif name == 'size':
                    style_name = 'font-size'

                if style_name:
                    del tag[name]
                    merge_styles[style_name] = value

            # Since the font tag has only above 3 possible attributes, it should
            # be empty now. If it's not, we should re-check the code below to
            # see whether things are
            if tag.attrs:
                raise Exception('font tag has unknown attributes: ' +
                                str(tag.attrs))
            # We have not checked whether merge_styles contain unneeded
            # attributes; we will 'mangle' the new tag again after merging the
            # styles into the destination tag. Also, unlike the 'else:' block
            # below we don't check if there are styles to merge ours _into_.

        else:
            self.mangle_attributes(tag)
            # Styles and classes need to be merged into the destination tag, if
            # that already has these attributes. If not, just move/merge the
            # whole attribute along with the others.
            if dest.get('style'):
                merge_styles = self.get_style_properties(tag)
            if dest.get('class'):
                merge_classes = tag.get('class')


        # Merge the attributes into the destination.
        for attr in tag.attrs:
            # One special case: <a name> becomes id. We've checked duplicates
            # already.
            dest_name = attr[0] if (tag_name != 'a' or attr[0] != 'name') else 'id'
            # Overwrite the value into the destination, except if:
            # - the destination is the child, which has the same attribute; then
            #   skip.
            # - the destination also has the 'style/class' attribute; then merge
            #   below.
            dest_value = dest.get(dest_name)
            if not (dest_value and (dest_is_child or
                                    attr[0] in ['style', 'class'])):
                dest[dest_name] = attr[1]

        # Merge classes into the destination.
        if merge_classes:
            # We know destination classes exist.
            classes = set(
                map(str.lower, re.split(r'\s+', dest.get('class')))
            ).union(set(
                map(str.lower, re.split(r'\s+', merge_classes))
            ))
            dest['class'] = ' '.join(classes)

        # Merge styles into the destination.
        if merge_styles:
            dest_styles = self.get_style_properties(dest)
            for name in merge_styles:
                # If the destination already has the property: overwrite child
                # value into parent, or skip if the destination is the child.
                if not (dest_is_child and name in dest_styles):
                    dest_styles[name] = merge_styles[name]
            # Reconstruct the style attribute and put it back into the
            # destination element.
            style = ''
            for name in dest_styles:
                if style != '':
                    style += '; '
                style += name + ': ' + dest_styles[name]
            dest['style'] = style

        # Now move the old tag content and remove the tag.
        if dest_is_new:
            self.move_contents_inside(tag, dest)
        else:
            # Move everything into the parent, just before the tag. (If the
            # destination is the child tag, "everything" includes the
            # destination.)
            self.move_contents_before(tag, tag)
        tag.extract()

        # It is possible that some styles that we copied from the font tag are
        # not needed. In order to not have to change more code: check
        # destination again.
        if tag_name == 'font':
            self.mangle_attributes(dest)

    def get_contents(self, tag, contents_type):
        """Get filtered contents of a tag.

        This exists for making code easier to read (by extracting the lambda
        from it) and easier to remember (i.e. the difference between t.findAll
        and t.contents)
        """
        if contents_type == 'nonwhitespace_string':
            # Return non-whitespace NavigableStrings.
            return tag.findAll(text=lambda x, r=self.rx_nbspace_only: r.match(x) == None, recursive=False)
        elif contents_type == 'tags':
            return tag.findAll(recursive=False)
        # Default, though we probably won't call the function for this:
        return tag.contents

    def move_contents_before(self, from_inside_tag, to_before_element):
        """Move all contents out of one tag, to just before another element."""
        self.move_contents_inside(from_inside_tag,
                                  to_before_element.parent,
                                  self.get_index_in_parent(to_before_element))

    def move_contents_inside(self, from_inside_tag, to_inside_tag,
                             insert_at_index=0, starting_from_index=0):
        """Move (last part of) contents out of one tag, to inside another tag.

        Contents (all or last part) can be inserted at a specified index;
        default at the start).
        """
        r = from_inside_tag.contents
        i = insert_at_index
        while len(r) > starting_from_index:
            # We are assuming that Beautifulsoup itself starts out having
            # maximum one consecutive NavigableString within a tag. It's easy
            # to write code which inadvertantly assumes this is always the case.
            # The below if/elif can be deleted, but they ease the adverse effect
            # that such buggy code would have.
            # Still, it's only a part solution / such code is considered buggy.
            # Because every tag.extract() command could leave two consecutive
            # NavigableStrings behind; there's nothing preventing that.
            # Tip for tracing such buggy code: (un)comment all from the 'if' to
            # 'else:' and re-run the script. The output should be the same.
            #if i > 0 and r[fromindex].__class__.__name__ == 'NavigableString'
            #and toinside.contents[i-1].__class__.__name__ == 'NavigableString':
                # Append the string to be inserted, to the string appearing
                # right before the destination. (Even though we always check
                # this, this condition should only be true when inserting the
                # first element.)
            #    toinside.contents[i-1].replaceWith(str(toinside.contents[i-1])
            #        + str(r[fromindex]))
            #    r[fromindex].extract()
            #elif len(r) == fromindex + 1 and i < len(toinside.contents) and
            #    r[fromindex].__class__.__name__ == 'NavigableString' and
            #    toinside.contents[i].__class__.__name__ == 'NavigableString':
                # Prepend the last string to be inserted to the string
                # appearing right after the destination (i.e. at the
                # destinaton's index).
            #    toinside.contents[i].replaceWith(str(r[fromindex]) + str(toinside.contents[i]))
            #    r[fromindex].extract()
            #else:
            to_inside_tag.insert(i, r[starting_from_index])
            i = i + 1

    def move_whitespace_to_parent(self, tag, remove_if_empty=True):
        """Move leading/trailing whitespace out of tag; remove empty tag.

        This function's logic is suitable for inline tags only. We assume that
        all kinds of whitespace may be moved outside inline tags, without this
        influencing formatting of the output. This includes both newlines
        (influencing formatting of the source HTML; we assume we never need
        newlines to stay just before inline-end tags) and <br>s.

        We do not want to end up inserting whitespace at the very beginning/end
        of an inline tag. That is: if our tag is e.g. at the very end of its
        parent, we don't want to move whitespace out into it(s end) - but rather
        into a further ancestor tag. (Otherwise the end result would depend on
        which tags we process before others.)
        """
        r = tag.contents
        # Remove tags containing nothing.
        if not r:
            if remove_if_empty:
                tag.extract()
                return

        # Move all-whitespace contents (including <br>) to before. This could
        # change r, so loop.
        while self.regex_search(r[0], self.rx_spacehtml_only):
            # Find destination tag, and possibly destination string, to move our
            # whitespace to.
            t = tag
            while (t.previousSibling is None and
                   self.get_tag_name(t.parent) in self.inline_tag_names):
                # Parent is inline and we'd be inserting whitespace at its
                # start: continue to grandparent.
                t = t.parent
            dest_tag = t.parent
            possible_dest = t.previousSibling

            # Move full-whitespace string/tag to its destination.
            if (r[0].__class__.__name__ == 'Tag' or
                    possible_dest.__class__.__name__ != 'NavigableString'):
                # Move tag or full NavigableString into destination tag, either
                # after the previous sibling or (if that does not exist) at the
                # start. (The insert() command will implicitly remove it from
                # its old location.)
                dest_index = 0
                if possible_dest:
                    dest_index = self.get_index_in_parent(possible_dest) + 1
                dest_tag.insert(dest_index, r[0])
            else:
                # Prepend to existing string.
                possible_dest.replaceWith(str(possible_dest) + str(r[0]))
                # Remove existing NavigableString.
                r[0].extract()
            if not r:
                if remove_if_empty:
                    tag.extract()
                    return

        # Move whitespace part at start of NavigableString to before tag.
        m = self.regex_search(r[0], self.rx_nbspace_at_start)
        if m:
            # Find destination tag/string to move our whitespace to.
            t = tag
            while (t.previousSibling is None and
                   self.get_tag_name(t.parent) in self.inline_tag_names):
                t = t.parent
            dest_tag = t.parent
            possible_dest = t.previousSibling

            # Move whitespace string to its destination.
            if possible_dest.__class__.__name__ != 'NavigableString':
                # Insert new NavigableString into destination tag,either after
                # the previous sibling or (if that does not exist) at the start.
                element = NavigableString(m.group(1))
                dest_index = 0
                if possible_dest:
                    dest_index = self.get_index_in_parent(possible_dest) + 1
                dest_tag.insert(dest_index, element)
            else:
                # Append to existing NavigableString.
                possible_dest.replaceWith(str(possible_dest) + m.group(1))

            # Remove whitespace from the existing NavigableString.
            len_whitespace = len(m.group(1))
            s = str(r[0])
            r[0].replaceWith(s[len_whitespace : ])

        # Move all-whitespace contents (including <br>) to after. This could
        # change r, so loop. Because of above, we know r will never become
        # empty here.
        while self.regex_search(r[-1], self.rx_spacehtml_only):
            # Find destination tag, and possibly destination string, to move our
            # whitespace to.
            t = tag
            while (t.nextSibling is None and
                   self.get_tag_name(t.parent) in self.inline_tag_names):
                # Parent is inline and we'd be inserting whitespace at its end:
                # continue to grandparent.
                t = t.parent
            dest_tag = t.parent
            possible_dest = t.nextSibling

            # Move full-whitespace string/tag to its destination.
            if (r[-1].__class__.__name__ == 'Tag' or
                    possible_dest.__class__.__name__ != 'NavigableString'):
                # Move tag or full NavigableString into destination tag, either
                # before the next sibling or (if that does not exist) at the
                # end. (The insert() command will implicitly remove it from its
                # old location.)
                if possible_dest:
                    dest_index = self.get_index_in_parent(possible_dest)
                else:
                    dest_index = len(dest_tag.contents)
                dest_tag.insert(dest_index, r[-1])
            else:
                # Prepend to existing string.
                possible_dest.replaceWith(str(r[-1]) + str(possible_dest))
                # Remove existing NavigableString.
                r[-1].extract()

        # Move whitespace part at end of NavigableString to after tag.
        m = self.regex_search(r[-1], self.rx_nbspace_at_end)
        if m:
            # Find destination tag/string to move our whitespace to.
            t = tag
            while (t.nextSibling is None and
                   self.get_tag_name(t.parent) in self.inline_tag_names):
                t = t.parent
            dest_tag = t.parent
            possible_dest = t.nextSibling

            # Move whitespace string to its destination.
            if possible_dest.__class__.__name__ != 'NavigableString':
                # Insert new NavigableString into destination tag, either before
                # the next sibling or (if that does not exist) at the end.
                element = NavigableString(m.group(1))
                if possible_dest:
                    dest_index = self.get_index_in_parent(possible_dest)
                else:
                    dest_index = len(dest_tag.contents)
                dest_tag.insert(dest_index, element)
            else:
                # Prepend to existing NavigableString.
                possible_dest.replaceWith(m.group(1) + str(possible_dest))

            # Remove whitespace from the existing NavigableString.
            len_whitespace = len(m.group(1))
            s = str(r[-1])
            r[-1].replaceWith(s[ : -len_whitespace])

    def starts_rendered_line(self, element):
        """Determine if an element is on the beginning of a rendered line.

        This function assumes that all existing inline tags have non-whitespace
        contents and all non-inline elements take up the full vertical space for
        themselves (i.e. they start at a new line, and the content directly
        after them does too).
        """
        # If a previous element exists within the same parent, assume we're at
        # the start of a line if the element is non-inline, and we're not at the
        # start if the element is inline. (See assumption in docstring.)
        previous = element.previousSibling
        while previous is None:
            # If we're at the start of an inline tag, keep looking outside that
            # tag. If we're at the start of another tag, assume we're at the
            # start of a line.
            if not self.get_tag_name(element.parent) in self.inline_tag_names:
                at_line_start = True
                break
            # We also assume we will never get here with the very first element
            # in the document (because there's always a <head> which breaks this
            # loop).
            element = element.parent
            previous = element.previousSibling

        if previous != None:
            n = self.get_tag_name(previous)
            at_line_start = not(n == '' or n in self.inline_tag_names)
        return at_line_start

    def dedupe_whitespace(self, navstr):
        """De-duplicate whitespace in NavigableString.

        Later adjacent NavigableStrings get merged into the provided one if
        possible. We determine if the string always gets rendered at the start
        of a line, and adjust for this in the de-duplication of non-breaking
        whitespace & the keeping of a newline as the deduped string.
        """
        at_line_start = self.starts_rendered_line(navstr)
        result = str(navstr)
        # Merge consecutive strings.
        nexttag = navstr.nextSibling
        while (nexttag != None
               and nexttag.__class__.__name__ == 'NavigableString'):
            result += str(nexttag)
            nexttag.extract()
            nexttag = navstr.nextSibling

        # Dedupe spaces at start of our string.
        # - Replace single &nbsp;s too, unless our constant says not to OR our
        #   string is at the start of a rendered line.
        # - Replace _by_ single space, unless the string includes a newline and
        #   is at the start of a rendered line.
        rx = self.rx_multispace_at_start
        if self.dedupe_nbsp and not at_line_start:
            rx = self.rx_multinbspace_at_start
        m = rx.search(result)
        if m:
            replacement = ' '
            if at_line_start and m.group(1).find('\n') != -1:
                replacement = '\n'
            # This sub() does not need restrictions because we know it replaces
            # maximum one occurrence.
            result = rx.sub(replacement, result)

        # Dedupe spaces elsewhere in our string. Since we won't touch the very
        # start of our string anymore, the replacement is never '\n'.
        if self.dedupe_nbsp and at_line_start:
            # We want to deduplicate &nbsp;s too, but not those wich occur in
            # whitespace at the very start of our string. (We just explicitly
            # prevented replacing those, above.) We have a special regex for
            # this. We should be able to just replace all occurrences with one
            # command (like in the 'else' below) but \1 does not seem to work
            # as replacement? So loop and replace one by one.
            m = self.regex_search(result, self.rx_multinbspace_not_at_start)
            while m:
                result = self.rx_multinbspace_not_at_start.sub(
                    m.group(1) + ' ', result, 1)
                m = self.regex_search(result, self.rx_multinbspace_not_at_start)
        else:
            # Deduplicate single &nbsp;s too, unless our constant says not to OR
            # we've already just done it.
            rx = self.rx_multinbspace if self.dedupe_nbsp else self.rx_multispace
            result = rx.sub(' ', result)

        if result != str(navstr):
            navstr.replaceWith(result)

    def strip_leading_whitespace(self, navstr, including_newline=None):
        """Strip whitespace from the start of a NavigableString.

        If the whole string is whitespace (also if that is non-breaking), then
        remove the NavigableString and repeat the stripping if the next sibling
        is also NavigableString. Stop if any tag is encountered (including <br>)

        <br> and &nbsp; have effect at the start of a string so do not remove
        them; do not look behind &nbsp;, because
        - a single space after &nbsp; has effect so should not be stripped;
        - there is other code to dedupe spaces. We strip but don't dedupe.

        If newlines are found, keep one at most, but:
        - If including_newline == True, never keep a newline. (Always strip it.)
        - If including_newline == False, always add a newline at the start even
        if there was none in the beginning.
        """
        force_strip_newline = including_newline is True
        readd_newline = including_newline is False
        match = self.regex_search(navstr, self.rx_spaces_at_start)
        while match:
            replacement = ''
            if not force_strip_newline and navstr.find('\n') != -1:
                replacement = '\n'
            force_strip_newline = False
            if match.group(1) == str(navstr):
                # NavigableString contains only whitespace, fully being removed.
                #  We need to loop back and check again. Also, if we encountered
                # a newline then add at most one back at the start.
                nxt = navstr.nextSibling
                navstr.extract()
                navstr = nxt
                if replacement:
                    readd_newline = True
                match = None
                if (navstr != None and
               	        navstr.__class__.__name__ == 'NavigableString'):
                    match = self.regex_search(navstr, self.rx_spaces_at_start)
            elif replacement != match.group(1):
                # String is only part whitespace: strip/replace it and be done.
                # Handle the adding-of-newlines here.
                if readd_newline:
                    replacement = '\n'
                # If replacement is already '\n', don't add an extra one.
                if replacement:
                    readd_newline = False
                s = str(navstr)
                navstr.replaceWith(replacement + s[ len(match.group(1)) : ])
                match = None
            else:
                # replacement == '\n' and navstr starts with a single newline
                # followed by a non-space. (Because replacement == '' will
                # always be matched by the 'elif'.) Don't loop, and don't
                # bother checking about the \n.
                match = None
                readd_newline = False
        if readd_newline and including_newline != True:
            # As noted: re-add newline.
            if navstr is None:
                element = NavigableString('\n')
                navstr.parent.insert(0, element)
            elif navstr.__class__.__name__ == 'Tag':
                element = NavigableString('\n')
                navstr.parent.insert(self.get_index_in_parent(navstr), element)
            else:
                navstr.replaceWith('\n' + str(navstr))

    def strip_trailing_whitespace(self, navstr, including_newline=None):
        """Strip whitespace from the end of a NavigableString.

        If the whole string is whitespace (also if that is non-breaking), then
        remove the NavigableString and repeat the stripping if the previous
        sibling is also a NavigableString. Stop if any tag is encountered
        (including <br>).

        If newlines are found, keep one at most, but:
        - If including_newline == True, never keep a newline. (Always strip it.)
        - If including_newline == False, always add a newline at the end even if
        there was none in the beginning.
        """
        force_strip_newline = including_newline is True
        readd_newline = including_newline is False
        match = self.regex_search(navstr, self.rx_nbspace_at_end)
        while match:
            replacement = ''
            if not force_strip_newline and navstr.find('\n') != -1:
                replacement = '\n'
            force_strip_newline = False
            if match.group(1) == str(navstr):
                # NavigableString contains only whitespace, fully being removed.
                # We need to loop back and check again. Also, if we encountered
                # a newline then add at most one back at the end.
                prev = navstr.previousSibling
                navstr.extract()
                navstr = prev
                if replacement:
                    readd_newline = True
                match = None
                if (navstr != None and
                        navstr.__class__.__name__ == 'NavigableString'):
                    match = self.regex_search(navstr, self.rx_nbspace_at_end)
            elif replacement != match.group(1):
                # String is only part whitespace: strip/replace it and be done.
                # Handle the adding-of-newlines here.
                if readd_newline:
                    replacement = '\n'
                # If replacement is already '\n', don't add an extra one.
                if replacement:
                    readd_newline = False
                s = str(navstr)
                navstr.replaceWith(s[ : -len(match.group(1))] + replacement)
                match = None
            else:
                # replacement == '\n' and navstr ends with a non-space followed
                # by a single newline. (Because replacement == '' will always
                #  be matched by the 'elif'.) Don't loop, and don't bother
                # checking about the \n.
                match = None
                readd_newline = False
        if readd_newline and including_newline != True and navstr != None:
            # As noted: re-add newline unless NavigableString ends in newline.
            # (And unless tag contents are now empty.)
            if navstr.__class__.__name__ == 'Tag':
                elm = NavigableString('\n')
                navstr.parent.insert(self.get_index_in_parent(navstr) + 1, elm)
            else:
                s = str(navstr)
                if s[-1] != '\n':
                    navstr.replaceWith(s + '\n')

    def strip_non_inline_whitespace(self, tag, including_newline=None):
        """Remove whitespace from start / end of a tag's contents.

        If newlines are found, keep one at most, but:
        - If including_newline == True never keep newlines. (Always strip them.)
        - If including_newline == False, always add a newline at the start/end
        even if there was none in the beginning.

        This should not be done for inline tags. It assumes:
        - We don't need to recurse into child tags (because we already handled
          those). In other words: please call movewhitespacetoparent() on inline
          child tags, before calling this function.
        - Our contents could be only whitespace/<br>. In that case we still
        won't remove the empty tags; they might still mean something (because of
        being a non-inline tag, possibly having an 'id' or whatever else).
        """
        # We really should not have empty contents by now, but still:
        r = tag.contents
        if r:
            # Strip whitespace from end. Assume:
            # - There can be multiple NavigableStrings at the end.
            # - If the last encountered tag is <br>, we don't need to look
            #   further before it, because other code will do that. ( / has
            #   done that.)
            # - One <br> at the end of a non-inline tag does not do anything in
            #   the rendered document, so we should remove it.
            # - Any &nbsp;: same.
            readd_newline = False
            if (r[-1].__class__.__name__ == 'Tag' and
                    self.get_tag_name(r[-1]) == 'br'):
                r[-1].extract()
            elif (self.regex_search(r[-1], self.rx_nbspace_only) and
                  len(r) > 1 and
                  r[-2].__class__.__name__ == 'Tag' and
                  self.get_tag_name(r[-2]) == 'br'):
                # Remove both the spaces and this one <br>, then check the next.
                # If there was a newline somewhere after the <br> then add that
                # after the last remaining tag/string - except if the string
                # already ends in a newline.
                readd_newline = r[-1].find('\n') != -1
                r[-1].extract()
                r[-1].extract()
            # Now strip (more) spaces from the end of the last
            # NavigableString(s), but no (more) <br>. (If the tag is now
            # totally empty, don't readd newline.)
            if r:
                trailing_including_newline = including_newline
                if including_newline is None and readd_newline:
                    trailing_including_newline = False
                self.strip_trailing_whitespace(r[-1], trailing_including_newline)
                # Also strip from the start.
                if r:
                    self.strip_leading_whitespace(r[0], including_newline)

    def split_paragraphs_with_double_br(self):
        """Replace (exactly) two consecutive <br>s inside <p>, by </p><p>

        This is most effective after doing any calls to
        - move_whitespace_to_parent(), which moves <br>s from child tags
          directly into the <p> where possible)
        - mangle_tag() (which does effectively the same by removing child tag)
        - dedupe_whitespace() (because this method is lazy and assumes the only
          possible whitespace between <br>s is a single newline).
        """
        for br in self.soup.findAll('br'):
            found = False
            # Check if previous is not a <br>...
            lf = None
            e = br.previousSibling
            if (e != None and e.__class__.__name__ == 'NavigableString' and
                    str(e) == '\n'):
                e = e.previousSibling
            if (e != None and e.__class__.__name__ == 'Tag' and
                    self.get_tag_name(e) != 'br'):
                # ...and the next is a <br>...
                br2 = br.nextSibling
                if (br2 != None and br2.__class__.__name__ == 'NavigableString'
                        and str(br2) == '\n'):
                    lf = br2
                    br2 = br2.nextSibling
                if (br2 != None and br2.__class__.__name__ == 'Tag' and
                        self.get_tag_name(br2) == 'br'):
                    # ...and the one after that is not a <br>...
                    next_element = br2.nextSibling
                    if (next_element != None
                        and next_element.__class__.__name__ == 'NavigableString'
                        and str(next_element) == '\n'):
                        next_element = next_element.nextSibling
                    if (next_element != None
                            and next_element.__class__.__name__ == 'Tag'
                            and self.get_tag_name(e) != 'br'):
                        # ...and the parent is a <p>: (Note we only replace if
                        # <p> is a direct parent. A double <br> inside an
                        # inline tag like <em> is semantically almost the same,
                        # but it's too much work to then also close and reopen
                        # the inline tags.)
                        parent_tag = br.parent
                        if self.get_tag_name(parent_tag) == 'p':
                            # Too much indenting here. Do an 'if found'.
                            found = True
            if found:
                # We have exactly two <br>s, inside a <p>. Move contents after
                # t2 to a new paragraph.
                if next_element is None:
                    # The two br's were at the end of a paragraph. Strange. Move
                    # them outside (just after) the paragraph.
                    parent_tag.parent.insert(
                        self.get_index_in_parent(parent_tag) + 1, br2)
                    if lf != None:
                        parent_tag.parent.insert(
                            self.get_index_in_parent(parent_tag) + 1, lf)
                    parent_tag.parent.insert(
                        self.get_index_in_parent(parent_tag) + 1, br)
                else:
                    # Insert a newline and a new paragraph just
                    # after our paragraph. (We always insert one
                    # newline, regardless whether the <br>s are
                    # followed by newlines.)
                    i = self.get_index_in_parent(parent_tag) + 1
                    p2 = Tag(self.soup, 'p')
                    parent_tag.parent.insert(i, p2)
                    e = NavigableString('\n')
                    parent_tag.parent.insert(i, e)
                    # Move all content after the second <br> into
                    # the new paragraph, after removing a newline
                    # if that follows the second <br>.
                    if (next_element != None and
                            next_element.__class__.__name__ == 'NavigableString'
                            and str(next_element) == '\n'):
                        next_element.extract()
                    self.move_contents_inside(parent_tag, p2, 0,
                                              self.get_index_in_parent(br2) + 1)
                    # Remove the <br>s and the newline between them (if any).
                    br2.extract()
                    br.extract()
                    if lf != None:
                        lf.extract()

    def remove_single_cell_table(self, table):
        """Delete tables with one <tr> having one <td>; these are useless.

        (Take their contents out of the tables.)
        """
        r1 = self.get_contents(table, 'nonwhitespace_string')
        r2 = self.get_contents(table, 'tags')
        if len(r1) + len(r2) == 0:
            table.extract()
        else:
            r_tr = table.findAll('tr', recursive=False)
            if len(r_tr) == 1:

                r1 = self.get_contents(r_tr[0], 'nonwhitespace_string')
                r2 = self.get_contents(r_tr[0], 'tags')
                if len(r1) + len(r2) == 0:
                    table.extract()
                else:
                    r_td = r_tr[0].findAll('td', recursive=False)
                    if not r_td:
                        table.extract()
                    elif len(r_td) == 1:

                        # Content inside a 'td' is left aligned by default;
                        # accomodate for that. (check_alignment() can delete it
                        # later if needed.)
                        e = Tag(self.soup, 'div')
                        e['style'] = 'text-align: left'
                        table.parent.insert(self.get_index_in_parent(table), e)
                        self.move_contents_inside(r_td[0], e)
                        table.extract()

    def check_convert_table_to_list(self, table, li_img_re):
        """Convert table with a specific layout to ul/li's.

        MS Frontpage (or at least one of its users) uses tables as a way to make
        bullet points: one table with each row having 2 fields, the first of
        which only contains a 'bullet point image'. If this table adheres to
        that structure, replace it with <ul><li>.

        The 'ul' gets a style 'text-align: left'; this can later be removed
        again by check_alignment() if it's unnecessary.

        bullet_img_re is a compiled regular expression which must match the
        'src' of the images in the first column, for replacement to happen.
        """
        r1 = self.get_contents(table, 'nonwhitespace_string')
        r2 = self.get_contents(table, 'tags')
        r_tr = table.findAll('tr', recursive=False)
        if len(r1) + len(r2) != len(r_tr):
            raise Exception('Parse error: table contains other direct tags '
                            'than tr.')

        all_bullets = 1
        for tr in r_tr:
            # 'Break' (skip further processing) if any row does not have all
            # bullets.
            if all_bullets:
                all_bullets = 0

                r1 = self.get_contents(tr, 'nonwhitespace_string')
                r2 = self.get_contents(tr, 'tags')
                r_td = tr.findAll('td', recursive=False)
                if len(r1) + len(r2) != len(r_td):
                    raise Exception('Parse error: tr contains other direct '
                                    'tags than td.')

                if len(r_td) == 2:
                    # The first 'td' must contain a sigle 'img' tag.
                    r1 = self.get_contents(r_td[0], 'nonwhitespace_string')
                    r2 = self.get_contents(r_td[0], 'tags')
                    if (not r1 and len(r2) == 1 and
                            self.get_tag_name(r2[0]) == 'img' and
                            li_img_re.search(r2[0]['src'])):
                        all_bullets = 1

        if all_bullets:
            # Looped through all rows; we know if this table contains only
            # bullets. Insert ul just before the table.
            ul = Tag(self.soup, 'ul')
            # Content inside a 'td' is left aligned by default.
            ul['style'] = 'text-align: left'
            i = self.get_index_in_parent(table)
            table.parent.insert(i, ul)
            # Pad the inside of the ul (at start and end) with \n.
            element = NavigableString('\n')
            ul.insert(0, element)
            # Insert li's and move all the contents from the second td's into
            # there. Other code will take care of straightening out e.g.
            # spacing. (Is it always legal to just 'dump everything' inside a
            # li? Let's hope so.)
            i = 1
            for tr in r_tr:
                e = Tag(self.soup, 'li')
                ul.insert(i, e)
                r_td = tr.findAll('td', recursive=False)
                self.move_contents_inside(r_td[1], e)
                e = NavigableString('\n')
                ul.insert(i + 1, e)
                i = i + 2
            table.extract()
