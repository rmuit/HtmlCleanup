#!/usr/bin/env python2.7
"""A script to Read old MS FrontPage HTML document and tidy it up.

This should be usable on other types of HTML too; try it. If it's not perfect:
see if you can make changes. The code in this script is readable top-down and is
commented well. (Most of the nitty gritty work is separated out into classes.)

This so far needs BeautifulSoup v3, which is not available for Python 3.
"""

import re
from optparse import OptionParser
from BeautifulSoup import BeautifulSoup, Tag, Comment
from htmlcleanup import HtmlCleanupHelper
from soupcleanup import SoupCleanupHelper

# Some constants used later:
# - Remove empty paragraphs after <ul>. (It _seems_ this is something you would
#   always want to arrange in styling... but removing them may change vertical
#   spacing / make things inconsistent, it if there are <ul>s with and without
#   empty paragraphs below them.
c_remove_empty_paragraphs_under_blocks = True
# - Images which should be converted to 'li' tag when found inside a table with
#   a specific structure. Format: regex.
c_img_bullet_re = r'(rom|exp)bul.?.?\.gif$'
# - font tags to remove if they have the following families. Other <font> tags
#   will be converted to spans, with their attribute names converted to style
#   names. It often happens that MSFT uses two font definitions: one with
#   several families and one with only the first. To remove both, specify both.
c_font_faces_to_remove = ['Book Antiqua, Times New Roman, Times',
                          'Book Antiqua']

# We have no options yet, but optparse is a convenient way of printing usage,
# if invoked with -h.
a = OptionParser(usage='usage: %prog htmlfile',
                 description="Input argument is a 'non-clean' HTML file; a "
                 'cleaned-up version is printed to stdout.')
(options, args) = a.parse_args()
if len(args) != 1:
    print "Number of command line arguments must be 1!"
    a.print_help()
    exit()

html = open(args[0]).read()
html = html.replace('\r\n', '\n')

## Change the HTML before it gets parsed by BeautifulSoup.

helper = HtmlCleanupHelper()

# Clean up completely wrong HTML before parsing - #1:
#
# Strip superfluous font tag, because FrontPage does things like
# <font> <center> </font> </center>, which makes HTMLTidy/BeautifulSoup
# wronlgy 'correct' stuff that would be fine if those font tags weren't there.
# Also, accommodate for recursive font tags... because _in between_ these
# these idiotic tags there may be legit ones.
#
# This is a bit arbitrary because it only strips font tags with _only_ the
# 'face' attribute. For better or worse, we so far are assuming that these are
# the only "completely wrong" tags, and others can/will be handled by
# BeautifulSoup (stripped/converted to spans if necessary) later.
if c_font_faces_to_remove:
    tag_contents = []
    for font_family in c_font_faces_to_remove:
        tag_contents.append('face="' + font_family + '"')
    html = helper.remove_tags(html, 'font', tag_contents)

# <o:p> tags are a mystery. So far, I've seen empty ones, ones with a small
# amount of whitespace content, and single opening tags without a closing tag.
html = helper.remove_tags(html, 'o:p')

# Clean up completely wrong HTML before parsing - #2:
#
# Solve <b><p > .... </b> ... </p> by putting <b> inside <p>. (If we don't,
# BeatifulSoup will put a </p> before the </b> which will mess up formatting.)
#
# We might abstract this into a CleanupHelper method if we want to do other
# combinations of tags.
rx1 = re.compile(r'\<b\>(\s*\<p.*?\>)(.*?)\<\/b>', re.S)
for r in rx1.finditer(html):
    if r.group(2).find('/p>') == -1:
        html = html[:r.start()] + r.group(1) + '<b>' + html[r.start(2):]
        # since html stays just as long, the finditer will be OK?

## Now do tidying work using BeautifulSoup.

soup = BeautifulSoup(html)
helper = SoupCleanupHelper(soup)
if c_font_faces_to_remove:
    # Set 'face' attributes for removal, just in case there are <font> tags
    # which have extra attributes in addition to 'face', because those would not
    # have been matched / removed by HtmlCleanupHelper.remove_tags().
    helper.remove_attributes['font'] = {}
    helper.remove_attributes['font']['face'] = c_font_faces_to_remove

## Soup part 1: remove some structural things, and unify for compliant HTML.

# Delete all script tags.
for tag in soup.findAll('script'):
    tag.extract()

# Delete comments; we assume we never want to keep MS Frontpage comments.
for element in soup.findAll(text=lambda text: isinstance(text, Comment)):
    element.extract()

# Replace b->strong and i->em, for XHTML compliance, and so that we're sure we
# are not skipping tags in the code below.
for tag in soup.findAll('b'):
    e = Tag(soup, 'strong')
    tag.parent.insert(helper.get_index_in_parent(tag), e)
    helper.move_contents_inside(tag, e)
    tag.extract()
for tag in soup.findAll('i'):
    e = Tag(soup, 'em')
    tag.parent.insert(helper.get_index_in_parent(tag), e)
    helper.move_contents_inside(tag, e)
    tag.extract()


## Soup part 2: work on large block elements in document structure.

# Delete tables with one TR having one TD; these are useless.
#
# (Take their contents out of the tables.)
for table in soup.findAll('table'):
    helper.remove_single_cell_table(table)

# Our HTML uses tables as a way to make bullet points:
# one table with each row having 2 fields, the first of which only
# contains a 'bullet point image'.
# Replace those tables by <ul><li> structures.
regex = re.compile(c_img_bullet_re)
for table in soup.findAll('table'):
    helper.check_convert_table_to_list(table, regex)

# Delete/change superfluous alignment attributes (and <center> tags sometimes).
helper.check_alignment(soup.body, 'left')


## Soup part 3: change/remove/unify contents of other tags.
#
# Generally try to unify stuff before removing/changing stuff.

# Some 'a' tags have 'strong' tags surrounding them, and some have 'strong' tags
# inside them. Normalize this so that 'a' is always inside.
for tag in soup.findAll('a'):
    r1 = tag.findAll('strong', recursive=False)
    if r1:
        r2 = tag.findAll(recursive=False)
        if (len(r1) == len(r2) and
                not helper.get_contents(tag, 'nonwhitespace_string')):
            # All tags are 'strong' and all navigablestrings are whitespace.
            # Delete the 'strong'. (Can be a chain of multiple, in extreme weird
            # cases).
            for element in r1:
                helper.move_contents_before(element, element)
                element.extract()
            # Make 'strong' tag and move element inside it
            element = Tag(soup, 'strong')
            tag.parent.insert(helper.get_index_in_parent(tag), element)
            element.insert(0, tag)
# Maybe TODO: have a class for 'strong' links? That would remove the need for:
# Links are rendered in bold, by default.
# Some links have a 'b' around it, which makes no visual difference but
# is an inconsistency in the document structure. Remove it.
#r = soup.findAll('a')
#for e in r:
#  s = e.parent.__repr__()
#  if s[0:3] == '<b>' and s[-4:] == '</b>':
    # the 'b' may have more content than just the link. As long as that's all
    # whitespace, there is still no difference in taking it away.
#    ok = 1
#    for ee in e.parent.contents:
#      if ee != e and not(helper.regex_search(ee, rx_spacehtml_only)):
#        ok = 0
#        break
#    if ok:
#      ee = e.parent
#      helper.move_contents_before(ee, ee)
#      ee.extract()

# Move leading/trailing whitespace out of inline tags into parents; remove empty
# tags.
#
# This could be useful to do before mangle_tag() stuff, because then we don't
# have to deal with attributes inside these empty tags; they will just be
# removed. We assume these inline tags don't contain attributes like 'id' which
# must be preserved. (This is why we won't do 'div' and 'a' here. These could be
# processed despite not being pure-inline tags, but only if they don't have an
# 'id', and preferrably after mangle_tag(). But right now we won't; it seems too
# much trouble for little/no gain.)
for tag_name in helper.inline_tag_names:
    for tag in soup.findAll(tag_name):
        helper.move_whitespace_to_parent(tag, tag_name != 'a')

# Check if we can get rid of some inline tags if we move their attributes to a
# child/parent; also normalize their attributes.
#
# <font> must come first; it has special handling so it's always removed (and
# replaced by <span> if necessary). We're not sure of what definition we adhere
# to yet:
# - <div> is not an inline element but we assume we can remove it for MS
#   Frontpage pages without trouble. (If this turns out not to be the case, we
#   might need to change check_alignment() because that may leave empty <div>s
#   around which are in fact unnecessary.)
# - <p> is also not an inline element, but we assume we can remove it if it is
#   the single tag wrapped in another element (like e.g. blockquote, li). (Or
#   wrapping a single other element, but that probably won't happen.) We must
#   leave it at the end though, because we want other tags to be removed in
#   favor of <p>.
for tag_name in ['font', 'div', 'span', 'a', 'p']:
    for tag in soup.findAll(tag_name):
        helper.mangle_tag(tag)

# Normalize other tags' attributes if necessary.
#
# (h2 / h4 tags with cleanable attributes found in one website. Adding h3.)
for tag_name in ['p', 'h2', 'h3', 'h4']:
    for t in soup.findAll(tag_name):
        helper.mangle_attributes(t)

# Now that spacing is moved to where it should be and unnecessary tags are gone:

# Remove duplicate spacing and unnecessary newlines.
#
# This implies first concatenating any adjacent NavigableStrings (which can
# occur where we've extract()ed tags).
#
# Remove newlines except if the string is at the start of a rendered line. (This
# includes newlines inside <p>s; see newline policy. Also we've seen e.g. h2
# tags with two newlines in the middle of the title so we explicitly want to do
# those.) We won't recurse into child tags; we don't dare to assume that no tags
# will have problems with whitespace removal - e.g. <pre>.)
for tag_name in helper.inline_tag_names + \
    ['p', 'h2', 'h3', 'h4', 'li', 'blockquote']:
    for tag in soup.findAll(tag_name):
        r = tag.contents
        i = 0
        while i < len(r):
            # Skip to next string.
            if r[i].__class__.__name__ == 'NavigableString':
                # This may shorten r, but does not extract r[i].
                helper.dedupe_whitespace(r[i])
            i += 1

# Remove unnecessary whitespace at start/end of non-inline tags.
#
# This does not make a difference for rendering; it just makes for neater HTML.
# (We've often seen useless &nbsp;s at the end of lines (li/p) which are just
# ugly. We just do the rest too because why not.)
for tag_name in ['p', 'h2', 'h3', 'h4', 'li', 'blockquote', 'div']:
    for tag in soup.findAll(tag_name):
        helper.strip_non_inline_whitespace(tag,
                                           True if tag_name == 'li' else None)
helper.strip_non_inline_whitespace(soup.body)

# In the same vein, remove unnecessary whitespace just before and after <br>s.
#
# This is partly duplicate because most NavigableStrings around <br> have
# been processed by the previous code block. This also does <br>s that are
# not inside (the first level of) the tags specified just above.
for tag in soup.findAll('br'):
    element = tag.previousSibling
    if element != None and element.__class__.__name__ == 'NavigableString':
        helper.strip_trailing_whitespace(element)
    element = tag.nextSibling
    if element != None and element.__class__.__name__ == 'NavigableString':
        helper.strip_leading_whitespace(element)

# If there's one empty paragraph after 'block elements', remove it.
# (We assume that such whitespacea should be implemented in a unified way using
# CSS in the target, not using HTML.)
if c_remove_empty_paragraphs_under_blocks:
    for tag_name in ['table', 'ul']:
        for tag in soup.findAll(tag_name):
            element = tag.nextSibling
            while helper.regex_search(element, helper.rx_nbspace_only):
                element = element.nextSibling
            if helper.get_tag_name(element) == 'p' and not element.contents:
                element.extract()

# Remove empty paragraphs at the end of the document. (Same reason.)
#
# Because of earlier calls, paragraphs have no whitespace inside them anymore if
# they are empty, and whitespace after the last paragraphs can only be single
# newlines.
last_tag = soup.body.contents[-1]
if last_tag.__class__.__name__ == 'NavigableString' and str(last_tag) == '\n':
    last_tag = last_tag.previousSibling
while helper.get_tag_name(last_tag) == 'div':
    last_tag = last_tag.contents[-1]
    if last_tag.__class__.__name__ == 'NavigableString' and str(last_tag) == '\n':
        last_tag = last_tag.previousSibling
while helper.get_tag_name(last_tag) == 'p' and not last_tag.contents:
    tag = last_tag.previousSibling
    last_tag.extract()
    last_tag = tag

# BeautifulSoup (at least 3.x tested so far) outputs <br />, which is kind-of
# illegal and certainly unnecessary as HTML.
print str(soup).replace('<br />', '<br>')
